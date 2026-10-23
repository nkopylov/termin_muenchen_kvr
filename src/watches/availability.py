# ABOUTME: Availability queries against the city's available-calendar endpoint for watches.
# ABOUTME: Fetches a captcha token right before each call and retries once on a token error.

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from src import services_manager
from src.munich_api_client import get_api_client
from src.services import captcha_token
from src.watches import when
from src.watches.slots import (
    SlotTime,
    WatchSnapshot,
    calendar_times,
    slots_in_scope,
    times_for_offices,
)
from src.watches.when import effective_window

logger = logging.getLogger(__name__)

COMBINATION_ERROR = "invalidLocationAndServiceCombination"
TOKEN_MIN_TTL = 30.0


class ApiError(StrEnum):
    TOKEN = "token"
    COMBINATION = "combination"
    UNAVAILABLE = "unavailable"  # the city API answered with an HTTP 5xx
    CAPTCHA = "captcha"  # no captcha token could be obtained
    OTHER = "other"


@dataclass(frozen=True)
class CallResult:
    ok: bool
    data: dict | None
    error: ApiError | None
    status: int | None = None

    def describe(self) -> str:
        """The failure reason as shown in logs and admin health alerts"""
        if self.error is ApiError.UNAVAILABLE:
            return f"city API unavailable (HTTP {self.status})"
        if self.error is ApiError.CAPTCHA:
            return "captcha unavailable"
        if self.error is ApiError.OTHER:
            if self.status is None:
                return "city API unreachable"
            return f"city API error (HTTP {self.status})"
        return str(self.error)


@services_manager.per_catalog
def public_office_ids(service_id: int) -> frozenset[int]:
    """Offices with a public relation to the service that exist in the catalog, without
    those that disable the service (the city website hides them and they get no slots)."""
    payload = services_manager.get_full_payload()
    bookable = {
        office["id"]
        for office in payload.get("offices", [])
        if service_id not in (office.get("disabledByServices") or ())
    }
    return frozenset(
        r["officeId"]
        for r in payload.get("relations", [])
        if r["serviceId"] == service_id
        and r.get("public", True)
        and r["officeId"] in bookable
    )


@services_manager.per_catalog
def _shared_booking_ids(service_id: int) -> dict[int, frozenset[int]]:
    """Each public office of the service mapped to the public offices that share its
    booking queue (sharedBookingOfficeIds), itself included."""
    public = public_office_ids(service_id)
    groups: dict[int, frozenset[int]] = {}
    for office in services_manager.get_full_payload().get("offices", []):
        if office["id"] not in public:
            continue
        shared = set(office.get("sharedBookingOfficeIds") or ()) & public
        groups[office["id"]] = frozenset(shared | {office["id"]})
    return groups


def office_choices(service_id: int) -> list[int]:
    """The service's public offices as the city website offers them: offices sharing a
    booking queue are one choice, named by their lowest id."""
    return list(_office_choices(service_id))


@services_manager.per_catalog
def _office_choices(service_id: int) -> tuple[int, ...]:
    return tuple(
        sorted({min(group) for group in _shared_booking_ids(service_id).values()})
    )


def booking_group(service_id: int, office_id: int) -> list[int]:
    """office_id and the public offices of the service that share its booking queue."""
    group = _shared_booking_ids(service_id).get(office_id, frozenset())
    return sorted(group | {office_id})


def watch_office_ids(rec) -> list[int]:
    """The watch's office with the offices sharing its queue, or every public office."""
    if rec.office_id is not None:
        return booking_group(rec.service_id, rec.office_id)
    return sorted(public_office_ids(rec.service_id))


def _params(service_id, office_ids, start, end, slots_day, token) -> dict:
    params = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "officeIds": ",".join(str(o) for o in office_ids),
        "serviceIds": str(service_id),
        "serviceCounts": "1",
        "captchaToken": token,
    }
    if slots_day is not None:
        params["slotsStartDate"] = slots_day.isoformat()
        params["slotsEndDate"] = slots_day.isoformat()
    return params


async def fetch_calendar(
    service_id: int,
    office_ids: list[int],
    start: date,
    end: date,
    slots_day: date | None = None,
) -> CallResult:
    for attempt in range(2):
        token = await captcha_token.get_token(min_ttl=TOKEN_MIN_TTL)
        if token is None:
            return CallResult(False, None, ApiError.CAPTCHA)
        params = _params(service_id, office_ids, start, end, slots_day, token)
        response = await asyncio.to_thread(
            get_api_client().get_result, "available-calendar/", params
        )
        if response.ok:
            return CallResult(True, response.data, None)
        if captcha_token.is_token_error(response.error_codes):
            captcha_token.invalidate()
            if attempt == 0:
                continue
            return CallResult(False, None, ApiError.TOKEN)
        if COMBINATION_ERROR in response.error_codes:
            return CallResult(False, None, ApiError.COMBINATION)
        if response.status is not None and response.status >= 500:
            return CallResult(False, None, ApiError.UNAVAILABLE, response.status)
        return CallResult(False, None, ApiError.OTHER, response.status)
    return CallResult(False, None, ApiError.TOKEN)


def _merge_calendars(calendars: list[dict]) -> dict:
    by_day: dict[str, dict] = {}
    for cal in calendars:
        for entry in cal.get("availableDays") or []:
            merged = by_day.setdefault(
                entry["date"], {"date": entry["date"], "providerIDs": "", "offices": []}
            )
            providers = [p for p in merged["providerIDs"].split(",") if p]
            providers += [
                p
                for p in str(entry.get("providerIDs") or "").split(",")
                if p and p not in providers
            ]
            merged["providerIDs"] = ",".join(providers)
            merged["offices"].extend(entry.get("offices") or [])
    return {"availableDays": [by_day[d] for d in sorted(by_day)]}


async def fetch_calendar_with_fallback(
    service_id: int,
    office_ids: list[int],
    start: date,
    end: date,
    slots_day: date | None = None,
) -> tuple[CallResult, set[int]]:
    """fetch_calendar; on a combination error query each office alone and merge the results.
    Returns the result and the offices dropped for failing with a combination error."""
    result = await fetch_calendar(service_id, office_ids, start, end, slots_day)
    if result.error is not ApiError.COMBINATION:
        return result, set()

    calendars, dropped = [], set()
    for office_id in office_ids:
        single = await fetch_calendar(service_id, [office_id], start, end, slots_day)
        if single.ok:
            calendars.append(single.data)
        elif single.error is ApiError.COMBINATION:
            dropped.add(office_id)
        else:
            return single, dropped
    if dropped:
        logger.warning(
            f"Service {service_id}: offices {sorted(dropped)} rejected as combination"
        )
    if not calendars:
        return CallResult(False, None, ApiError.COMBINATION), dropped
    return CallResult(True, _merge_calendars(calendars), None), dropped


async def fetch_day_times(
    service_id: int, office_ids: list[int], day: date
) -> tuple[SlotTime, ...] | None:
    """All appointment times of `day` at `office_ids`; () when the day is gone, None on failure."""
    result, _ = await fetch_calendar_with_fallback(
        service_id, office_ids, day, day, slots_day=day
    )
    if not result.ok:
        return None
    entry = next(
        (
            e
            for e in result.data.get("availableDays") or []
            if e.get("date") == day.isoformat()
        ),
        None,
    )
    if entry is None:
        return ()
    wanted = set(office_ids)
    return tuple(
        sorted(
            SlotTime(int(ts), int(o["officeId"]))
            for o in entry.get("offices") or []
            if int(o["officeId"]) in wanted
            for ts in o.get("appointments") or []
        )
    )


async def snapshot_for_watch(rec, today: date) -> WatchSnapshot:
    """Check one watch now (used for the immediate check after creating or changing it)."""
    window = effective_window(rec.when, today)
    offices = watch_office_ids(rec)
    if window is None or window.is_empty or not offices:
        return WatchSnapshot(when.utcnow(), True)

    result, dropped = await fetch_calendar_with_fallback(
        rec.service_id, offices, window.start, window.end
    )
    if not result.ok:
        return WatchSnapshot(when.utcnow(), False)

    in_scope = set(offices) - dropped
    slots = slots_in_scope(result.data, in_scope, window)
    if not slots:
        return WatchSnapshot(when.utcnow(), True)

    earliest = min(s.day for s in slots)
    times = calendar_times(result.data, earliest, in_scope)
    if times is None:
        day_offices = sorted(s.office_id for s in slots if s.day == earliest)
        fetched = await fetch_day_times(rec.service_id, day_offices, earliest)
        if fetched is None:
            return WatchSnapshot(when.utcnow(), False)
        times = times_for_offices(fetched, in_scope)
    return WatchSnapshot(when.utcnow(), True, slots, times)
