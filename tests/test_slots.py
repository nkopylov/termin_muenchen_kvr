# ABOUTME: Tests for slot identity, snapshot serialization and calendar filtering.
# ABOUTME: Calendars are built in the shape the city's available-calendar endpoint returns.

from datetime import date, datetime

import pytest

from src.watches.slots import (
    BOOK_BUTTON_DAYS,
    Slot,
    SlotTime,
    WatchSnapshot,
    calendar_times,
    decode_slots,
    encode_slots,
    parse_slot_key,
    prune_past,
    slot_key,
    slots_in_scope,
    snapshot_from_json,
    snapshot_to_json,
    times_for_offices,
    top_days,
)
from src.watches.when import Window
from tests.fakes import calendar

D1 = date(2026, 10, 29)
D2 = date(2026, 11, 26)
D3 = date(2026, 12, 3)
D4 = date(2026, 12, 10)


class TestSlotKeys:
    def test_round_trip(self):
        slot = Slot(D1, 102526)
        assert slot_key(slot) == "2026-10-29@102526"
        assert parse_slot_key("2026-10-29@102526") == slot

    def test_encode_is_sorted_json(self):
        raw = encode_slots(frozenset({Slot(D2, 1), Slot(D1, 2), Slot(D1, 1)}))
        assert raw == '["2026-10-29@1", "2026-10-29@2", "2026-11-26@1"]'
        assert decode_slots(raw) == frozenset({Slot(D2, 1), Slot(D1, 2), Slot(D1, 1)})

    def test_empty(self):
        assert encode_slots(frozenset()) == "[]"
        assert decode_slots("[]") == frozenset()

    @pytest.mark.parametrize("raw", ["not json", '["bad"]', '{"a": 1}'])
    def test_decode_rejects_garbage(self, raw):
        with pytest.raises((ValueError, TypeError)):
            decode_slots(raw)


class TestSnapshot:
    def test_days_and_earliest(self):
        snap = WatchSnapshot(
            datetime(2026, 10, 22, 10),
            True,
            frozenset({Slot(D2, 1), Slot(D1, 1), Slot(D1, 2)}),
        )
        assert snap.days() == [D1, D2]
        assert snap.earliest_day == D1

    def test_empty_earliest_is_none(self):
        assert WatchSnapshot(datetime(2026, 10, 22), True).earliest_day is None

    def test_json_round_trip(self):
        snap = WatchSnapshot(
            datetime(2026, 10, 22, 10, 5, 7),
            True,
            frozenset({Slot(D1, 1), Slot(D2, 2)}),
            (SlotTime(1793260800, 1), SlotTime(1793261100, 1)),
        )
        assert snapshot_from_json(snapshot_to_json(snap)) == snap

    def test_failed_snapshot_round_trip(self):
        snap = WatchSnapshot(datetime(2026, 10, 22, 10), False)
        assert snapshot_from_json(snapshot_to_json(snap)) == snap

    def test_from_json_none(self):
        assert snapshot_from_json(None) is None
        assert snapshot_from_json("") is None

    def test_from_json_garbage_raises(self):
        with pytest.raises(ValueError):
            snapshot_from_json("{broken")


class TestTopDaysAndPrune:
    def test_top_days_takes_earliest_distinct_days(self):
        slots = frozenset(
            {Slot(D4, 1), Slot(D1, 1), Slot(D1, 2), Slot(D2, 1), Slot(D3, 1)}
        )
        assert BOOK_BUTTON_DAYS == 3
        assert top_days(slots) == frozenset({D1, D2, D3})
        assert top_days(slots, 1) == frozenset({D1})
        assert top_days(frozenset()) == frozenset()

    def test_prune_past_keeps_today(self):
        slots = frozenset({Slot(D1, 1), Slot(D2, 1)})
        assert prune_past(slots, D2) == frozenset({Slot(D2, 1)})
        assert prune_past(slots, date(2026, 10, 1)) == slots


class TestSlotsInScope:
    def test_filters_offices_and_window(self):
        cal = calendar(
            days={
                "2026-10-29": [102526, 10489],
                "2026-11-26": [54261],
                "2027-06-01": [102526],
            }
        )
        window = Window(date(2026, 10, 22), date(2027, 4, 20))
        assert slots_in_scope(cal, {102526, 54261}, window) == frozenset(
            {Slot(D1, 102526), Slot(D2, 54261)}
        )

    def test_window_edges_inclusive(self):
        cal = calendar(days={"2026-10-29": [1], "2026-11-26": [1]})
        assert slots_in_scope(cal, {1}, Window(D1, D2)) == frozenset(
            {Slot(D1, 1), Slot(D2, 1)}
        )

    def test_empty_calendar(self):
        assert slots_in_scope({"availableDays": []}, {1}, Window(D1, D2)) == frozenset()
        assert slots_in_scope({}, {1}, Window(D1, D2)) == frozenset()


class TestCalendarTimes:
    def test_all_relevant_offices_have_times(self):
        cal = calendar(
            days={"2026-10-29": [1, 2, 3]},
            times={"2026-10-29": [(300, 2), (100, 1), (200, 1), (50, 3)]},
        )
        assert calendar_times(cal, D1, {1, 2}) == (
            SlotTime(100, 1),
            SlotTime(200, 1),
            SlotTime(300, 2),
        )

    def test_none_when_one_relevant_office_lacks_times(self):
        cal = calendar(days={"2026-10-29": [1, 2]}, times={"2026-10-29": [(100, 1)]})
        assert calendar_times(cal, D1, {1, 2}) is None
        assert calendar_times(cal, D1, {1}) == (SlotTime(100, 1),)

    def test_none_when_day_has_no_times(self):
        cal = calendar(days={"2026-10-29": [1]})
        assert calendar_times(cal, D1, {1}) is None

    def test_day_missing_from_calendar(self):
        cal = calendar(days={"2026-10-29": [1]}, times={"2026-10-29": [(1, 1)]})
        assert calendar_times(cal, D2, {1}) is None

    def test_times_for_offices(self):
        times = (SlotTime(1, 1), SlotTime(2, 2), SlotTime(3, 1))
        assert times_for_offices(times, {1}) == (SlotTime(1, 1), SlotTime(3, 1))
        assert times_for_offices(times, set()) == ()
