# ABOUTME: Tests for availability queries: token per call, token-error retry, combination errors,
# ABOUTME: per-office fallback and building a watch snapshot. City API and captcha are faked.

from datetime import date

import pytest

from src.munich_api_client import ApiResponse
from src.repositories import WatchRecord
from src.services import captcha_token
from src.watches import availability
from src.watches.availability import ApiError, CallResult
from src.watches.slots import Slot, SlotTime
from src.watches.when import PRESETS, WhenSpec
from tests.fakes import calendar

TODAY = date(2026, 10, 22)
SID = 1063475
OFFICES = [102522, 102523, 10489, 10313237]


class FakeApi:
    def __init__(self):
        self.calls: list[dict] = []
        self.replies: list = []

    def get_result(self, endpoint, params):
        self.calls.append({"endpoint": endpoint, **params})
        reply = self.replies.pop(0)
        return reply(params) if callable(reply) else reply


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(availability, "get_api_client", lambda: fake)
    return fake


@pytest.fixture
def tokens(monkeypatch):
    state = {"issued": 0, "invalidated": 0, "fail": False, "min_ttls": []}

    async def get_token(min_ttl=30.0):
        state["min_ttls"].append(min_ttl)
        if state["fail"]:
            return None
        state["issued"] += 1
        return f"t{state['issued']}"

    def invalidate():
        state["invalidated"] += 1

    monkeypatch.setattr(captcha_token, "get_token", get_token)
    monkeypatch.setattr(captcha_token, "invalidate", invalidate)
    return state


@pytest.fixture
def catalog(monkeypatch):
    from src import services_manager

    offices = [{"id": o, "name": f"Bürgerbüro {o}"} for o in OFFICES + [999]]
    relations = [{"serviceId": SID, "officeId": o, "public": True} for o in OFFICES]
    relations.append({"serviceId": SID, "officeId": 999, "public": False})
    payload = {
        "services": [{"id": SID, "name": "Wohnsitzanmeldung"}],
        "offices": offices,
        "relations": relations,
    }
    monkeypatch.setattr(services_manager, "_full_payload_cache", payload)
    monkeypatch.setattr(services_manager, "_services_cache", payload["services"])


def ok(data):
    return ApiResponse(data, 200, ())


def err(*codes):
    return ApiResponse(None, 400, codes)


def watch(office_id=None, when=PRESETS["asap"]) -> WatchRecord:
    return WatchRecord(
        id=1,
        user_id=1,
        service_id=SID,
        office_id=office_id,
        when=when,
        status="active",
        pause_reason=None,
        end_reason=None,
        ended_at=None,
        last_checked_at=None,
        snapshot=None,
        alerted=frozenset(),
        live=None,
        interacted_at=None,
    )


class TestOffices:
    def test_public_office_ids(self, catalog):
        assert availability.public_office_ids(SID) == set(OFFICES)
        assert availability.public_office_ids(12345) == set()

    def test_watch_office_ids(self, catalog):
        assert availability.watch_office_ids(watch()) == sorted(OFFICES)
        assert availability.watch_office_ids(watch(10489)) == [10489]

    def test_office_disabled_for_the_service_is_not_public(self, catalog, monkeypatch):
        from src import services_manager

        def disable_10489_for(*service_ids):
            payload = services_manager._full_payload_cache
            offices = [
                {**o, "disabledByServices": list(service_ids)}
                if o["id"] == 10489
                else o
                for o in payload["offices"]
            ]
            monkeypatch.setattr(
                services_manager, "_full_payload_cache", {**payload, "offices": offices}
            )

        disable_10489_for(SID, 1063441)
        assert availability.public_office_ids(SID) == set(OFFICES) - {10489}
        disable_10489_for(1063441)
        assert availability.public_office_ids(SID) == set(OFFICES)

    def test_shared_booking_group_is_one_choice(self, catalog):
        from src import services_manager

        shared = [10489, 10313237, 10491]
        for office in services_manager._full_payload_cache["offices"]:
            if office["id"] in (10489, 10313237):
                office["sharedBookingOfficeIds"] = shared
        assert availability.office_choices(SID) == [10489, 102522, 102523]
        assert availability.public_office_ids(SID) == set(OFFICES)

    def test_single_office_watch_queries_its_shared_booking_group(self, catalog):
        from src import services_manager

        shared = [10489, 10313237, 10491]
        for office in services_manager._full_payload_cache["offices"]:
            if office["id"] in (10489, 10313237):
                office["sharedBookingOfficeIds"] = shared
        # 10491 shares the queue but does not offer the service
        assert availability.watch_office_ids(watch(10313237)) == [10489, 10313237]
        assert availability.watch_office_ids(watch(10489)) == [10489, 10313237]
        assert availability.watch_office_ids(watch(102522)) == [102522]

    def test_choices_without_shared_groups_are_the_public_offices(self, catalog):
        assert availability.office_choices(SID) == sorted(OFFICES)
        assert availability.office_choices(12345) == []


@pytest.mark.asyncio
class TestFetchCalendar:
    async def test_params_and_token_fetched_right_before_call(self, api, tokens):
        api.replies.append(ok({"availableDays": []}))

        result = await availability.fetch_calendar(
            SID, [102522, 10489], date(2026, 10, 22), date(2027, 4, 20)
        )

        assert result == CallResult(True, {"availableDays": []}, None)
        [call] = api.calls
        assert call == {
            "endpoint": "available-calendar/",
            "startDate": "2026-10-22",
            "endDate": "2027-04-20",
            "officeIds": "102522,10489",
            "serviceIds": str(SID),
            "serviceCounts": "1",
            "captchaToken": "t1",
        }
        assert tokens["min_ttls"] == [30]

    async def test_slots_day(self, api, tokens):
        api.replies.append(ok({"availableDays": []}))
        await availability.fetch_calendar(SID, [1], TODAY, TODAY, slots_day=TODAY)
        assert (
            api.calls[0]["slotsStartDate"]
            == api.calls[0]["slotsEndDate"]
            == "2026-10-22"
        )

    async def test_token_error_once_invalidates_and_retries(self, api, tokens):
        api.replies += [err("captchaInvalid"), ok({"availableDays": []})]

        result = await availability.fetch_calendar(SID, [1], TODAY, TODAY)

        assert result.ok
        assert tokens["invalidated"] == 1
        assert [c["captchaToken"] for c in api.calls] == ["t1", "t2"]

    async def test_token_error_twice_is_token_error(self, api, tokens):
        api.replies += [err("captchaExpired"), err("captchaMissing")]
        result = await availability.fetch_calendar(SID, [1], TODAY, TODAY)
        assert result == CallResult(False, None, ApiError.TOKEN)
        assert len(api.calls) == 2

    async def test_combination_error(self, api, tokens):
        api.replies.append(err("invalidLocationAndServiceCombination"))
        result = await availability.fetch_calendar(SID, [1], TODAY, TODAY)
        assert result == CallResult(False, None, ApiError.COMBINATION)

    async def test_other_error(self, api, tokens):
        api.replies.append(ApiResponse(None, None, ()))
        assert (
            await availability.fetch_calendar(SID, [1], TODAY, TODAY)
        ).error is ApiError.OTHER

    async def test_no_token_is_captcha_without_call(self, api, tokens):
        tokens["fail"] = True
        result = await availability.fetch_calendar(SID, [1], TODAY, TODAY)
        assert result == CallResult(False, None, ApiError.CAPTCHA)
        assert result.describe() == "captcha unavailable"
        assert api.calls == []

    async def test_server_error_is_unavailable_with_status(self, api, tokens):
        api.replies.append(ApiResponse(None, 503, ()))
        result = await availability.fetch_calendar(SID, [1], TODAY, TODAY)
        assert result == CallResult(False, None, ApiError.UNAVAILABLE, 503)
        assert result.describe() == "city API unavailable (HTTP 503)"


@pytest.mark.asyncio
class TestFallback:
    async def test_combination_falls_back_per_office_and_merges(self, api, tokens):
        def per_office(params):
            office = int(params["officeIds"])
            if office == 3:
                return err("invalidLocationAndServiceCombination")
            return ok(
                calendar(
                    days={"2026-10-29": [office]},
                    times={"2026-10-29": [(100 + office, office)]},
                )
            )

        api.replies += [
            err("invalidLocationAndServiceCombination"),
            per_office,
            per_office,
            per_office,
        ]

        result, dropped = await availability.fetch_calendar_with_fallback(
            SID, [1, 2, 3], TODAY, date(2026, 12, 1)
        )

        assert result.ok
        assert dropped == {3}
        [day] = result.data["availableDays"]
        assert day["date"] == "2026-10-29"
        assert set(day["providerIDs"].split(",")) == {"1", "2"}
        assert {o["officeId"] for o in day["offices"]} == {"1", "2"}

    async def test_all_offices_fail_is_combination(self, api, tokens):
        api.replies += [err("invalidLocationAndServiceCombination")] * 3
        result, dropped = await availability.fetch_calendar_with_fallback(
            SID, [1, 2], TODAY, TODAY
        )
        assert result.error is ApiError.COMBINATION
        assert dropped == {1, 2}

    async def test_other_error_in_fallback_fails(self, api, tokens):
        api.replies += [
            err("invalidLocationAndServiceCombination"),
            ApiResponse(None, 500, ()),
            ok({"availableDays": []}),
        ]
        result, _ = await availability.fetch_calendar_with_fallback(
            SID, [1, 2], TODAY, TODAY
        )
        assert result.error is ApiError.UNAVAILABLE
        assert result.status == 500

    async def test_success_needs_no_fallback(self, api, tokens):
        api.replies.append(ok({"availableDays": []}))
        result, dropped = await availability.fetch_calendar_with_fallback(
            SID, [1, 2], TODAY, TODAY
        )
        assert result.ok and dropped == set()
        assert len(api.calls) == 1


@pytest.mark.asyncio
class TestDayTimes:
    async def test_times_of_requested_offices(self, api, tokens):
        api.replies.append(
            ok(
                calendar(
                    days={"2026-10-29": [1, 2]},
                    times={"2026-10-29": [(200, 2), (100, 1)]},
                )
            )
        )
        times = await availability.fetch_day_times(SID, [1, 2], date(2026, 10, 29))
        assert times == (SlotTime(100, 1), SlotTime(200, 2))
        assert api.calls[0]["slotsStartDate"] == "2026-10-29"

    async def test_day_gone_is_empty(self, api, tokens):
        api.replies.append(ok({"availableDays": []}))
        assert await availability.fetch_day_times(SID, [1], date(2026, 10, 29)) == ()

    async def test_failure_is_none(self, api, tokens):
        api.replies.append(ApiResponse(None, 500, ()))
        assert await availability.fetch_day_times(SID, [1], date(2026, 10, 29)) is None

    async def test_rejected_office_falls_back_per_office(self, api, tokens):
        def per_office(params):
            office = int(params["officeIds"])
            if office == 3:
                return err("invalidLocationAndServiceCombination")
            return ok(
                calendar(
                    days={"2026-10-29": [office]},
                    times={"2026-10-29": [(100 + office, office)]},
                )
            )

        api.replies += [err("invalidLocationAndServiceCombination")] + [per_office] * 3
        times = await availability.fetch_day_times(SID, [1, 2, 3], date(2026, 10, 29))
        assert times == (SlotTime(101, 1), SlotTime(102, 2))
        assert all(call["slotsStartDate"] == "2026-10-29" for call in api.calls)


@pytest.mark.asyncio
class TestSnapshotForWatch:
    async def test_any_office_snapshot_with_times_from_calendar(
        self, api, tokens, catalog
    ):
        api.replies.append(
            ok(
                calendar(
                    days={
                        "2026-10-29": [102522, 10489],
                        "2026-11-26": [102523],
                        "2027-06-01": [102522],
                    },
                    times={"2026-10-29": [(300, 10489), (100, 102522)]},
                )
            )
        )

        snap = await availability.snapshot_for_watch(watch(), TODAY)

        assert snap.ok
        assert snap.slots == frozenset(
            {
                Slot(date(2026, 10, 29), 102522),
                Slot(date(2026, 10, 29), 10489),
                Slot(date(2026, 11, 26), 102523),
            }
        )
        assert snap.earliest_times == (SlotTime(100, 102522), SlotTime(300, 10489))
        assert api.calls[0]["officeIds"] == ",".join(str(o) for o in sorted(OFFICES))
        assert api.calls[0]["endDate"] == "2027-04-20"
        assert len(api.calls) == 1

    async def test_missing_times_fetch_the_day(self, api, tokens, catalog):
        api.replies.append(
            ok(
                calendar(
                    days={"2026-10-30": [102522, 10489]},
                    times={"2026-10-30": [(100, 102522)]},
                )
            )
        )
        api.replies.append(
            ok(
                calendar(
                    days={"2026-10-30": [102522, 10489]},
                    times={"2026-10-30": [(100, 102522), (50, 10489)]},
                )
            )
        )

        snap = await availability.snapshot_for_watch(watch(), TODAY)

        assert snap.earliest_times == (SlotTime(50, 10489), SlotTime(100, 102522))
        assert api.calls[1]["officeIds"] == "10489,102522"
        assert api.calls[1]["slotsStartDate"] == "2026-10-30"

    async def test_single_office_and_window(self, api, tokens, catalog):
        spec = WhenSpec("before", date_to=date(2026, 11, 1))
        api.replies.append(
            ok(
                calendar(
                    days={"2026-10-29": [10489], "2026-11-26": [10489]},
                    times={"2026-10-29": [(5, 10489)]},
                )
            )
        )

        snap = await availability.snapshot_for_watch(watch(10489, spec), TODAY)

        assert snap.slots == frozenset({Slot(date(2026, 10, 29), 10489)})
        assert api.calls[0]["endDate"] == "2026-10-31"

    async def test_no_slots(self, api, tokens, catalog):
        api.replies.append(ok({"availableDays": []}))
        snap = await availability.snapshot_for_watch(watch(), TODAY)
        assert snap.ok and snap.slots == frozenset() and snap.earliest_times == ()

    async def test_range_beyond_the_horizon_needs_no_call(self, api, tokens, catalog):
        spec = WhenSpec("between", date_from=date(2028, 1, 1), date_to=date(2028, 2, 1))
        snap = await availability.snapshot_for_watch(watch(when=spec), TODAY)
        assert snap.ok and snap.slots == frozenset()
        assert api.calls == []

    async def test_failed_query_is_not_ok(self, api, tokens, catalog):
        api.replies.append(ApiResponse(None, 500, ()))
        snap = await availability.snapshot_for_watch(watch(), TODAY)
        assert snap.ok is False

    async def test_failed_day_times_is_not_ok(self, api, tokens, catalog):
        api.replies.append(ok(calendar(days={"2026-10-30": [102522]})))
        api.replies.append(ApiResponse(None, 500, ()))
        snap = await availability.snapshot_for_watch(watch(), TODAY)
        assert snap.ok is False

    async def test_passed_deadline_needs_no_call(self, api, tokens, catalog):
        snap = await availability.snapshot_for_watch(
            watch(when=WhenSpec("before", date_to=TODAY)), TODAY
        )
        assert snap.ok and snap.slots == frozenset()
        assert api.calls == []
