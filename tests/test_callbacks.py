# ABOUTME: Tests for callback data builders and the parser: size limit, round trip, patterns.
# ABOUTME: Every builder is exercised with the largest ids the bot can see (10 digits).

import re
from datetime import date

import pytest

from src.ui import callbacks as cb
from src.ui.callbacks import Cb, parse

BIG = 9_999_999_999
DAY = date(2026, 10, 29)

BUILT = [
    (cb.find_home(), Cb("f1", "home")),
    (cb.find_all(), Cb("f1", "all")),
    (
        cb.find_category("auslaenderbehoerde", 12),
        Cb("f1", "cat", ("auslaenderbehoerde", 12)),
    ),
    (cb.find_service(BIG), Cb("f1", "svc", (BIG,))),
    (cb.find_office(BIG, BIG), Cb("f1", "off", (BIG, BIG))),
    (cb.find_office(BIG, None), Cb("f1", "off", (BIG, 0))),
    (cb.find_when(BIG, BIG, "asap"), Cb("f1", "when", (BIG, BIG, "asap"))),
    (cb.find_when(BIG, None, "3m"), Cb("f1", "when", (BIG, 0, "3m"))),
    (cb.find_date(BIG, BIG, "b"), Cb("f1", "date", (BIG, BIG, "b"))),
    (cb.find_date(BIG, None, "r"), Cb("f1", "date", (BIG, 0, "r"))),
    (cb.find_edit(BIG), Cb("f1", "edit", (BIG,))),
    (cb.find_edit_when(BIG, "1m"), Cb("f1", "ewhen", (BIG, "1m"))),
    (cb.find_edit_date(BIG, "r"), Cb("f1", "edate", (BIG, "r"))),
    (cb.find_any(BIG), Cb("f1", "any", (BIG,))),
    (cb.find_cancel(), Cb("f1", "x")),
    (cb.watches_list(), Cb("w1", "list")),
    (cb.watch_pause(BIG), Cb("w1", "pause", (BIG,))),
    (cb.watch_resume(BIG), Cb("w1", "resume", (BIG,))),
    (cb.watch_stop(BIG), Cb("w1", "stop", (BIG,))),
    (cb.watch_stop_yes(BIG), Cb("w1", "stopy", (BIG,))),
    (cb.watch_stop_no(BIG), Cb("w1", "stopn", (BIG,))),
    (cb.settings_home(), Cb("s1", "home")),
    (cb.settings_forget(), Cb("s1", "forget")),
    (cb.settings_delete(), Cb("s1", "del")),
    (cb.settings_delete_yes(), Cb("s1", "dely")),
    (cb.settings_delete_no(), Cb("s1", "deln")),
    (cb.book_day(BIG, DAY), Cb("b1", "day", (BIG, DAY))),
    (cb.book_time(BIG, BIG), Cb("b1", "t", (BIG, BIG))),
    (cb.book_me(), Cb("b1", "me")),
    (cb.book_change(), Cb("b1", "chg")),
    (cb.book_ok(), Cb("b1", "ok")),
    (cb.book_cancel(), Cb("b1", "x")),
]


@pytest.mark.parametrize(("data", "expected"), BUILT)
def test_round_trip_and_size(data, expected):
    assert len(data.encode()) <= 64
    assert parse(data) == expected


def test_exact_formats():
    assert cb.find_category("ausweis", 0) == "f1:cat:ausweis:0"
    assert cb.find_office(1063475, None) == "f1:off:1063475:0"
    assert cb.find_when(1063475, 102526, "2w") == "f1:when:1063475:102526:2w"
    assert cb.book_day(17, DAY) == "b1:17:20261029"
    assert cb.book_time(102526, 1793260800) == "b1:t:102526:1793260800"
    assert cb.watch_stop(5) == "w1:stop:5"


@pytest.mark.parametrize(
    "data",
    [
        "",
        "f1",
        "f1:",
        "f1:nope",
        "f1:svc",
        "f1:svc:abc",
        "f1:svc:1:2",
        "f1:when:1:2:5y",
        "f1:date:1:2:z",
        "f1:ewhen:1:asap:extra",
        "w1:pause",
        "w1:stop:-1",
        "s1:unknown",
        "b1:1:2026102",
        "b1:1:20261340",
        "b1:t:1",
        "x1:home",
        "main_menu",
        "book_2026-10-25_102101_1064305",
    ],
)
def test_parse_rejects(data):
    assert parse(data) is None


def test_oversized_builder_raises():
    with pytest.raises(AssertionError):
        cb.find_category("x" * 60, 1)


@pytest.mark.parametrize(
    ("pattern", "matches", "rejects"),
    [
        (cb.FIND_RE, ["f1:home"], ["w1:list", "xf1:home"]),
        (cb.WATCH_RE, ["w1:list"], ["f1:home"]),
        (cb.SETTINGS_RE, ["s1:del"], ["f1:home"]),
        (cb.BOOK_DAY_RE, ["b1:17:20261029"], ["b1:t:1:2", "b1:17:2026102"]),
        (cb.BOOK_RE, ["b1:me", "b1:17:20261029"], ["book_x"]),
        (
            cb.LEGACY_BOOKING_RE,
            ["time_1796292600", "confirm_booking", "cancel_booking"],
            ["time_", "book_2026-10-25_1_2", "b1:x"],
        ),
        (
            cb.NAV_RE,
            ["f1:home", "w1:list", "s1:home", "lang:ru", "language"],
            ["b1:me", "languages", "main_menu"],
        ),
    ],
)
def test_patterns(pattern, matches, rejects):
    for data in matches:
        assert re.search(pattern, data), data
    for data in rejects:
        assert not re.search(pattern, data), data
