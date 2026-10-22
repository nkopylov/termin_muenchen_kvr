# ABOUTME: Tests for watch time specs: search windows, typed date parsing and validation.
# ABOUTME: Also covers how migrated user date ranges become a WhenSpec.

from datetime import date, timedelta

import pytest

from src.watches import when
from src.watches.when import (
    ASAP_HORIZON_DAYS,
    MAX_QUERY_DAYS,
    PRESETS,
    DateError,
    WhenSpec,
    Window,
    effective_window,
    migrated_when,
    parse_date_range,
    parse_user_date,
    validate_before,
    validate_between,
)

TODAY = date(2026, 10, 22)


class TestPresets:
    def test_values(self):
        assert PRESETS == {
            "asap": WhenSpec("asap"),
            "2w": WhenSpec("within", 14),
            "1m": WhenSpec("within", 30),
            "3m": WhenSpec("within", 90),
        }
        assert ASAP_HORIZON_DAYS == 180
        assert MAX_QUERY_DAYS == 364


class TestTodayBerlin:
    def test_returns_a_date(self):
        assert isinstance(when.today_berlin(), date)


class TestEffectiveWindow:
    def test_asap_rolls_with_today(self):
        assert effective_window(WhenSpec("asap"), TODAY) == Window(
            TODAY, TODAY + timedelta(days=180)
        )
        later = TODAY + timedelta(days=50)
        assert effective_window(WhenSpec("asap"), later).end == later + timedelta(
            days=180
        )

    @pytest.mark.parametrize("days", [14, 30, 90])
    def test_within(self, days):
        assert effective_window(WhenSpec("within", days), TODAY) == Window(
            TODAY, TODAY + timedelta(days=days)
        )

    def test_within_is_clipped_to_max_query_days(self):
        assert effective_window(
            WhenSpec("within", 500), TODAY
        ).end == TODAY + timedelta(days=364)

    def test_before_excludes_deadline(self):
        deadline = date(2026, 11, 15)
        assert effective_window(WhenSpec("before", date_to=deadline), TODAY) == Window(
            TODAY, date(2026, 11, 14)
        )

    def test_before_day_before_deadline_is_single_day(self):
        deadline = TODAY + timedelta(days=1)
        assert effective_window(WhenSpec("before", date_to=deadline), TODAY) == Window(
            TODAY, TODAY
        )

    @pytest.mark.parametrize("offset", [0, 1, 30])
    def test_before_ends_on_or_after_deadline(self, offset):
        spec = WhenSpec("before", date_to=TODAY - timedelta(days=offset))
        assert effective_window(spec, TODAY) is None

    def test_before_far_deadline_is_clipped(self):
        spec = WhenSpec("before", date_to=TODAY + timedelta(days=400))
        assert effective_window(spec, TODAY).end == TODAY + timedelta(days=364)

    def test_between_future(self):
        spec = WhenSpec(
            "between", date_from=date(2026, 11, 1), date_to=date(2026, 11, 15)
        )
        assert effective_window(spec, TODAY) == Window(
            date(2026, 11, 1), date(2026, 11, 15)
        )

    def test_between_start_in_past_is_clipped_to_today(self):
        spec = WhenSpec(
            "between", date_from=date(2026, 10, 1), date_to=date(2026, 11, 15)
        )
        assert effective_window(spec, TODAY) == Window(TODAY, date(2026, 11, 15))

    def test_between_last_day_is_today(self):
        spec = WhenSpec("between", date_from=date(2026, 10, 1), date_to=TODAY)
        assert effective_window(spec, TODAY) == Window(TODAY, TODAY)

    def test_between_ends_after_last_day(self):
        spec = WhenSpec(
            "between", date_from=date(2026, 10, 1), date_to=TODAY - timedelta(days=1)
        )
        assert effective_window(spec, TODAY) is None

    def test_between_far_end_is_clipped(self):
        spec = WhenSpec("between", date_from=TODAY, date_to=TODAY + timedelta(days=500))
        assert effective_window(spec, TODAY).end == TODAY + timedelta(days=364)

    def test_between_starting_beyond_the_horizon_is_empty_until_queryable(self):
        start = TODAY + timedelta(days=400)
        spec = WhenSpec("between", date_from=start, date_to=start + timedelta(days=30))
        assert effective_window(spec, TODAY).is_empty
        assert not effective_window(spec, start - timedelta(days=364)).is_empty
        assert not effective_window(PRESETS["asap"], TODAY).is_empty


class TestParseUserDate:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-11-15", date(2026, 11, 15)),
            ("2027-1-5", date(2027, 1, 5)),
            ("  2026-11-15 ", date(2026, 11, 15)),
            ("15.11.2026", date(2026, 11, 15)),
            ("5.1.2027", date(2027, 1, 5)),
            ("15.11.26", date(2026, 11, 15)),
            ("05.01.27", date(2027, 1, 5)),
        ],
    )
    def test_formats(self, text, expected):
        assert parse_user_date(text, TODAY) == expected

    def test_day_month_after_today_is_this_year(self):
        assert parse_user_date("15.11", TODAY) == date(2026, 11, 15)

    def test_day_month_of_today_is_today(self):
        assert parse_user_date("22.10", TODAY) == TODAY

    def test_day_month_passed_recently_stays_in_the_past(self):
        assert parse_user_date("21.10", TODAY) == date(2026, 10, 21)
        assert parse_user_date("22.9", TODAY) == date(2026, 9, 22)
        assert parse_user_date("28.12", date(2027, 1, 5)) == date(2026, 12, 28)

    def test_day_month_passed_long_ago_is_next_year(self):
        assert parse_user_date("21.9", TODAY) == date(2027, 9, 21)
        assert parse_user_date("1.3", TODAY) == date(2027, 3, 1)
        assert parse_user_date("5.1", date(2026, 12, 20)) == date(2027, 1, 5)

    def test_day_month_feb_29_picks_a_leap_year_occurrence(self):
        assert parse_user_date("29.02", date(2027, 3, 1)) == date(2028, 2, 29)

    @pytest.mark.parametrize(
        "text",
        [
            "31.02.2026",
            "2026-13-01",
            "2026-02-30",
            "hello",
            "",
            "15.11.2026 extra",
            "15/11/2026",
            "15.11.202",
            "32.1",
            "0.1.2027",
        ],
    )
    def test_invalid(self, text):
        assert parse_user_date(text, TODAY) is None


class TestParseDateRange:
    @pytest.mark.parametrize(
        "text",
        [
            "2026-11-01 - 2026-11-15",
            "2026-11-01 – 2026-11-15",
            "2026-11-01..2026-11-15",
            "2026-11-01 bis 2026-11-15",
            "2026-11-01 до 2026-11-15",
            "1.11 bis 15.11",
            "с 01.11.2026 до 15.11.2026",
            "01.11.26-15.11.26",
        ],
    )
    def test_two_tokens(self, text):
        assert parse_date_range(text, TODAY) == (date(2026, 11, 1), date(2026, 11, 15))

    @pytest.mark.parametrize(
        "text",
        [
            "2026-11-01",
            "2026-11-01 2026-11-15 2026-12-01",
            "from tomorrow",
            "",
        ],
    )
    def test_not_exactly_two_tokens(self, text):
        assert parse_date_range(text, TODAY) is None

    def test_invalid_token(self):
        assert parse_date_range("31.02.2026 - 15.03.2026", TODAY) is None

    def test_range_starting_today_as_day_month(self):
        assert parse_date_range("22.10 - 30.10", TODAY) == (TODAY, date(2026, 10, 30))
        assert validate_between(TODAY, date(2026, 10, 30), TODAY) is None

    def test_range_ending_today_as_day_month(self):
        assert parse_date_range("15.10 - 22.10", TODAY) == (date(2026, 10, 15), TODAY)


class TestValidate:
    def test_before_ok(self):
        assert validate_before(TODAY + timedelta(days=1), TODAY) is None
        assert validate_before(TODAY + timedelta(days=364), TODAY) is None

    @pytest.mark.parametrize("offset", [0, -1])
    def test_before_past(self, offset):
        assert validate_before(TODAY + timedelta(days=offset), TODAY) is DateError.PAST

    def test_before_too_far(self):
        assert validate_before(TODAY + timedelta(days=365), TODAY) is DateError.TOO_FAR

    def test_between_ok_and_start_in_past_accepted(self):
        assert validate_between(TODAY, TODAY, TODAY) is None
        assert (
            validate_between(
                TODAY - timedelta(days=10), TODAY + timedelta(days=5), TODAY
            )
            is None
        )
        assert validate_between(TODAY, TODAY + timedelta(days=364), TODAY) is None

    def test_between_order(self):
        assert (
            validate_between(
                TODAY + timedelta(days=5), TODAY + timedelta(days=4), TODAY
            )
            is DateError.ORDER
        )

    def test_between_past(self):
        assert (
            validate_between(
                TODAY - timedelta(days=5), TODAY - timedelta(days=1), TODAY
            )
            is DateError.PAST
        )

    def test_between_too_far(self):
        assert (
            validate_between(TODAY, TODAY + timedelta(days=365), TODAY)
            is DateError.TOO_FAR
        )

    def test_error_values(self):
        assert {e.value for e in DateError} == {"format", "past", "too_far", "order"}


class TestMigratedWhen:
    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (None, None),
            ("", ""),
            ("2026-11-01", None),
            (None, "2026-11-01"),
            ("x", "y"),
        ],
    )
    def test_missing_or_garbage_is_asap(self, start, end):
        assert migrated_when(start, end, TODAY) == WhenSpec("asap")

    def test_future_range_is_between_in_iso(self):
        assert migrated_when("2026-11-1", "2026-12-5", TODAY) == WhenSpec(
            "between", date_from=date(2026, 11, 1), date_to=date(2026, 12, 5)
        )

    def test_running_range_is_between(self):
        assert migrated_when("2026-10-01", "2026-12-05", TODAY) == WhenSpec(
            "between", date_from=date(2026, 10, 1), date_to=date(2026, 12, 5)
        )

    def test_past_range_is_asap(self):
        assert migrated_when("2026-01-01", "2026-03-01", TODAY) == WhenSpec("asap")

    def test_reversed_range_is_asap(self):
        assert migrated_when("2026-12-05", "2026-11-01", TODAY) == WhenSpec("asap")

    def test_default_180_day_range_is_asap(self):
        start = TODAY - timedelta(days=20)
        end = start + timedelta(days=180)
        assert migrated_when(start.isoformat(), end.isoformat(), TODAY) == WhenSpec(
            "asap"
        )

    def test_too_far_end_is_clipped(self):
        end = TODAY + timedelta(days=400)
        assert migrated_when("2026-11-01", end.isoformat(), TODAY) == WhenSpec(
            "between", date_from=date(2026, 11, 1), date_to=TODAY + timedelta(days=364)
        )

    def test_range_starting_beyond_query_horizon_is_kept_as_is(self):
        assert migrated_when("2028-01-01", "2028-02-01", TODAY) == WhenSpec(
            "between", date_from=date(2028, 1, 1), date_to=date(2028, 2, 1)
        )

    def test_range_starting_on_last_queryable_day_is_kept(self):
        start = TODAY + timedelta(days=364)
        end = TODAY + timedelta(days=400)
        assert migrated_when(start.isoformat(), end.isoformat(), TODAY) == WhenSpec(
            "between", date_from=start, date_to=start
        )
