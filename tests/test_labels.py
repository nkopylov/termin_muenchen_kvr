# ABOUTME: Tests for watch labels: service and office names, time, dates, "ago", summary and state.
# ABOUTME: Uses the shared city catalog fixture with real service ids and office names.

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from src.repositories import WatchRecord
from src.watches import labels
from src.watches.labels import (
    POPULAR_SERVICE_IDS,
    ago_label,
    date_label,
    day_label,
    office_label,
    service_label,
    short_date_label,
    watch_state,
    watch_summary,
    when_label,
    where_label,
)
from src.watches.slots import Slot, WatchSnapshot
from src.watches.when import PRESETS, WhenSpec

pytestmark = pytest.mark.usefixtures("catalog")


def rec(**kwargs) -> WatchRecord:
    base = WatchRecord(
        id=1,
        user_id=1,
        service_id=1063475,
        office_id=None,
        when=PRESETS["asap"],
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
    return replace(base, **kwargs)


class TestServiceLabel:
    def test_popular_ids_in_order(self):
        assert POPULAR_SERVICE_IDS == (
            10339028,
            10339027,
            10502137,
            1063475,
            1063441,
            1063453,
            1071896,
            1064305,
        )

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_every_popular_id_has_a_short_label(self, lang):
        for service_id in POPULAR_SERVICE_IDS:
            label = service_label(service_id, lang)
            assert label and len(label) <= 60

    def test_localized(self):
        assert service_label(1063453, "en") == "Passport (Reisepass)"
        assert service_label(1063453, "ru") == "Паспорт (Reisepass)"

    def test_other_service_uses_german_name(self):
        assert service_label(1071907, "ru") == "Einbürgerung"

    def test_long_name_truncated(self, catalog):
        catalog["services"].append({"id": 5, "name": "A" * 80})
        label = service_label(5, "en")
        assert len(label) == 60 and label.endswith("…")

    def test_not_escaped(self, catalog):
        catalog["services"].append({"id": 6, "name": "A & <B>"})
        assert service_label(6, "en") == "A & <B>"

    @pytest.mark.parametrize(
        ("lang", "text"), [("en", "Service 7"), ("ru", "Услуга 7")]
    )
    def test_unknown(self, lang, text):
        assert service_label(7, lang) == text


class TestOfficeLabel:
    def test_strips_buergerbuero_prefix(self):
        assert office_label(102526, 1063475, "en") == "Forstenrieder Allee"

    def test_other_names_kept(self):
        assert office_label(10461, 10339028, "en") == (
            "Servicestelle für Zuwanderung und Einbürgerung"
        )

    def test_same_name_offices_numbered_by_id(self):
        assert office_label(10489, 1063475, "en") == "Ruppertstraße · 1"
        assert office_label(10313237, 1063475, "en") == "Ruppertstraße · 2"

    def test_without_service_no_numbers(self):
        assert office_label(10489) == "Ruppertstraße"

    def test_offices_sharing_a_booking_queue_are_one_place(self, catalog):
        for office in catalog["offices"]:
            if office["id"] in (10489, 10313237):
                office["sharedBookingOfficeIds"] = [10489, 10313237, 10491]
        assert office_label(10489, 1063475, "en") == "Ruppertstraße"
        assert office_label(10313237, 1063475, "en") == "Ruppertstraße"

    def test_office_whose_queue_is_named_differently_is_numbered(self, catalog):
        third = 20000000
        catalog["offices"].append({"id": third, "name": "Bürgerbüro Ruppertstraße"})
        catalog["relations"].append(
            {"serviceId": 1063475, "officeId": third, "public": True}
        )
        for office in catalog["offices"]:
            if office["id"] in (102522, third):
                office["sharedBookingOfficeIds"] = [102522, third]
        assert office_label(third, 1063475, "en") == "Ruppertstraße · 3"
        assert office_label(10489, 1063475, "en") == "Ruppertstraße · 1"
        assert office_label(102522, 1063475, "en") == "Orleansplatz"

    @pytest.mark.parametrize(
        ("lang", "text"), [(None, "Office 1"), ("ru", "Отделение 1")]
    )
    def test_unknown(self, lang, text):
        assert office_label(1, 1063475, lang) == text


class TestWhereAndWhen:
    def test_where(self):
        assert where_label(rec(), "en") == "Any office"
        assert where_label(rec(), "ru") == "Любое отделение"
        assert where_label(rec(office_id=54261), "en") == "Pasing"

    def test_where_names_the_only_office_of_a_service(self):
        assert where_label(rec(service_id=1064305), "en") == "KfZ Zulassungsstelle"
        assert where_label(rec(service_id=1064305), "ru") == "KfZ Zulassungsstelle"

    @pytest.mark.parametrize(
        ("spec", "en", "ru"),
        [
            (PRESETS["asap"], "as soon as possible", "как можно скорее"),
            (PRESETS["2w"], "within 2 weeks", "в ближайшие 2 недели"),
            (PRESETS["1m"], "within 1 month", "в ближайший месяц"),
            (PRESETS["3m"], "within 3 months", "в ближайшие 3 месяца"),
            (WhenSpec("within", 21), "within 21 days", "в ближайший 21 день"),
            (
                WhenSpec("before", date_to=date(2026, 11, 15)),
                "before 15.11.2026",
                "до 15.11.2026",
            ),
            (
                WhenSpec(
                    "between", date_from=date(2026, 11, 1), date_to=date(2026, 11, 15)
                ),
                "01.11.2026 – 15.11.2026",
                "с 01.11.2026 по 15.11.2026",
            ),
        ],
    )
    def test_when(self, spec, en, ru):
        assert when_label(spec, "en") == en
        assert when_label(spec, "ru") == ru


class TestDates:
    def test_day_label(self):
        assert day_label(date(2026, 10, 29), "en") == "Thu 29.10"
        assert day_label(date(2026, 10, 29), "ru") == "Чт 29.10"
        assert day_label(date(2026, 11, 2), "en") == "Mon 02.11"

    def test_date_labels(self):
        assert date_label(date(2026, 1, 5)) == "05.01.2026"
        assert short_date_label(date(2026, 1, 5)) == "05.01"

    @pytest.mark.parametrize(
        ("delta", "en", "ru"),
        [
            (timedelta(seconds=30), "just now", "только что"),
            (timedelta(minutes=1), "1 min ago", "1 минуту назад"),
            (timedelta(minutes=3, seconds=50), "3 min ago", "3 минуты назад"),
            (timedelta(minutes=59), "59 min ago", "59 минут назад"),
            (timedelta(hours=1), "1 hour ago", "1 час назад"),
            (timedelta(hours=23, minutes=59), "23 hours ago", "23 часа назад"),
            (timedelta(days=2), "2 days ago", "2 дня назад"),
            (timedelta(seconds=-5), "just now", "только что"),
        ],
    )
    def test_ago(self, delta, en, ru):
        assert ago_label(delta, "en") == en
        assert ago_label(delta, "ru") == ru


class TestSummaryAndState:
    def test_summary(self):
        assert watch_summary(rec(), "en") == (
            "Address registration (Anmeldung) · Any office · as soon as possible"
        )
        assert watch_summary(rec(office_id=10489, when=PRESETS["2w"]), "ru") == (
            "Регистрация по адресу (Anmeldung) · Ruppertstraße · 1 · в ближайшие 2 недели"
        )

    def test_state_not_checked_and_none(self):
        assert watch_state(rec(), "en") == "not checked yet"
        empty = WatchSnapshot(datetime(2026, 10, 22), True)
        assert watch_state(rec(snapshot=empty), "en") == "no free slots yet"

    def test_state_slots_counts_days(self):
        snap = WatchSnapshot(
            datetime(2026, 10, 22),
            True,
            frozenset(
                {
                    Slot(date(2026, 10, 29), 1),
                    Slot(date(2026, 10, 29), 2),
                    Slot(date(2026, 11, 3), 1),
                }
            ),
        )
        assert (
            watch_state(rec(snapshot=snap), "en") == "2 free days, earliest Thu 29.10"
        )
        assert (
            watch_state(rec(snapshot=snap), "ru")
            == "2 свободных дня, ближайший Чт 29.10"
        )

    @pytest.mark.parametrize(
        ("kwargs", "en"),
        [
            ({"status": "paused", "pause_reason": "user"}, "paused"),
            ({"status": "paused", "pause_reason": "blocked"}, "paused"),
            ({"status": "ended", "end_reason": "booked"}, "booked ✅"),
            (
                {"status": "ended", "end_reason": "deadline"},
                "ended: the date has passed",
            ),
            (
                {"status": "ended", "end_reason": "gone"},
                "ended: office no longer available",
            ),
            ({"status": "ended", "end_reason": "stopped"}, "stopped"),
        ],
    )
    def test_state_lifecycle(self, kwargs, en):
        assert watch_state(rec(**kwargs), "en") == en


def test_module_exports_where_label():
    assert labels.where_label is where_label
