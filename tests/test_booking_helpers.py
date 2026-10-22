# ABOUTME: Tests for the booking helpers: name and email validation, time labels and the time picker.
# ABOUTME: Owned by the booking stream.

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.commands.booking import (
    MAX_TIME_BUTTONS,
    format_time_on_date,
    format_time_on_long_date,
    is_valid_email,
    name_error,
    time_button_label,
    times_markup,
)
from src.watches.slots import SlotTime

BERLIN = ZoneInfo("Europe/Berlin")
FORSTENRIEDER = 102526
ORLEANSPLATZ = 102522
RUPPERT_1 = 10489
WOHNSITZ = 1063475


def ts(hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 10, 29, hour, minute, tzinfo=BERLIN).timestamp())


class TestNameError:
    @pytest.mark.parametrize("name", ["Ivan", "", "   ", "Anna-Maria"])
    def test_single_word_is_not_a_full_name(self, name):
        assert name_error(name) == "booking.name_not_full"

    def test_two_short_words_are_too_short(self):
        assert name_error("I P") == "booking.name_too_short"

    @pytest.mark.parametrize(
        "name", ["Ivan Petrov", "Li Na", "Anna Maria Schmidt", "李 明明"]
    )
    def test_full_names_pass(self, name):
        assert name_error(name) is None


class TestIsValidEmail:
    @pytest.mark.parametrize(
        "email",
        [
            "user@example.com",
            "test.user@domain.co.uk",
            "name+tag@test.org",
            "first_last%x@sub.example.de",
        ],
    )
    def test_valid(self, email):
        assert is_valid_email(email)

    @pytest.mark.parametrize(
        "email",
        [
            "notanemail",
            "missing@domain",
            "no.at.sign.com",
            "@nodomain.com",
            "two@@example.com",
            "spaces in@example.com",
            "user@example.c",
            "",
        ],
    )
    def test_invalid(self, email):
        assert not is_valid_email(email)


class TestTimeFormatting:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [("en", "Wed 05.03, 09:05"), ("ru", "Ср 05.03, 09:05")],
    )
    def test_time_on_date(self, lang, expected):
        dt = datetime(2025, 3, 5, 9, 5, tzinfo=BERLIN)
        assert format_time_on_date(dt, lang) == expected

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [
            ("en", "09:05 on Wednesday, March 5, 2025"),
            ("ru", "среда, 5 марта 2025, 09:05"),
        ],
    )
    def test_time_on_long_date(self, lang, expected):
        dt = datetime(2025, 3, 5, 9, 5, tzinfo=BERLIN)
        assert format_time_on_long_date(dt, lang) == expected


@pytest.mark.usefixtures("catalog")
class TestTimePicker:
    def test_label_is_the_berlin_clock_time(self):
        slot = SlotTime(ts(9, 30), FORSTENRIEDER)
        assert (
            time_button_label(slot, WOHNSITZ, show_office=False, lang="en") == "09:30"
        )

    def test_label_names_the_office_when_several_are_watched(self):
        slot = SlotTime(ts(9, 30), FORSTENRIEDER)
        assert (
            time_button_label(slot, WOHNSITZ, show_office=True, lang="en")
            == "09:30 · Forstenrieder Allee"
        )

    def test_label_disambiguates_offices_with_the_same_name(self):
        slot = SlotTime(ts(11), RUPPERT_1)
        assert (
            time_button_label(slot, WOHNSITZ, show_office=True, lang="en")
            == "11:00 · Ruppertstraße · 1"
        )

    @pytest.mark.parametrize(
        ("lang", "cancel"), [("en", "❌ Cancel"), ("ru", "❌ Отмена")]
    )
    def test_two_times_per_row_then_cancel(self, lang, cancel):
        times = (
            SlotTime(ts(9), FORSTENRIEDER),
            SlotTime(ts(9, 5), ORLEANSPLATZ),
            SlotTime(ts(9, 10), FORSTENRIEDER),
        )

        markup = times_markup(times, WOHNSITZ, show_office=False, lang=lang)

        rows = [
            [(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard
        ]
        assert rows == [
            [
                ("09:00", f"b1:t:{FORSTENRIEDER}:{ts(9)}"),
                ("09:05", f"b1:t:{ORLEANSPLATZ}:{ts(9, 5)}"),
            ],
            [("09:10", f"b1:t:{FORSTENRIEDER}:{ts(9, 10)}")],
            [(cancel, "b1:x")],
        ]

    def test_times_with_office_names_one_per_row(self):
        times = (SlotTime(ts(9), FORSTENRIEDER), SlotTime(ts(9, 5), ORLEANSPLATZ))

        markup = times_markup(times, WOHNSITZ, show_office=True, lang="en")

        assert [len(row) for row in markup.inline_keyboard] == [1, 1, 1]

    def test_at_most_twelve_times(self):
        times = tuple(SlotTime(ts(8, m), FORSTENRIEDER) for m in range(0, 60, 3))

        markup = times_markup(times, WOHNSITZ, show_office=False, lang="en")

        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert MAX_TIME_BUTTONS == 12
        assert data[:-1] == [f"b1:t:{FORSTENRIEDER}:{t.ts}" for t in times[:12]]
