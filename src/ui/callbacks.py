# ABOUTME: Callback data scheme of inline buttons: builders, a parser and handler patterns.
# ABOUTME: The digit in each prefix is the scheme version; Telegram limits data to 64 bytes.

import re
from dataclasses import dataclass
from datetime import date, datetime

MAX_CALLBACK_BYTES = 64

FIND_RE = r"^f1:"
WATCH_RE = r"^w1:"
SETTINGS_RE = r"^s1:"
BOOK_DAY_RE = r"^b1:\d+:\d{8}$"
BOOK_RE = r"^b1:"
NAV_RE = r"^(f1|w1|s1):|^lang:|^language$"
# Booking buttons of messages sent before the "b1:" scheme
LEGACY_BOOKING_RE = r"^time_\d+$|^confirm_booking$|^cancel_booking$"

WHEN_PRESETS = ("asap", "2w", "1m", "3m")
DATE_MODES = ("b", "r")  # before a date, range of dates


@dataclass(frozen=True)
class Cb:
    scope: str  # "f1" | "w1" | "s1" | "b1"
    action: str
    args: tuple = ()


def _build(*parts: object) -> str:
    data = ":".join(str(p) for p in parts)
    assert len(data.encode()) <= MAX_CALLBACK_BYTES, data
    return data


# f1: find flow


def find_home() -> str:
    return _build("f1", "home")


def find_all() -> str:
    return _build("f1", "all")


def find_category(category_id: str, page: int) -> str:
    return _build("f1", "cat", category_id, page)


def find_service(service_id: int) -> str:
    return _build("f1", "svc", service_id)


def find_office(service_id: int, office_id: int | None) -> str:
    return _build("f1", "off", service_id, office_id or 0)


def find_when(service_id: int, office_id: int | None, preset: str) -> str:
    return _build("f1", "when", service_id, office_id or 0, preset)


def find_date(service_id: int, office_id: int | None, mode: str) -> str:
    return _build("f1", "date", service_id, office_id or 0, mode)


def find_edit(watch_id: int) -> str:
    return _build("f1", "edit", watch_id)


def find_edit_when(watch_id: int, preset: str) -> str:
    return _build("f1", "ewhen", watch_id, preset)


def find_edit_date(watch_id: int, mode: str) -> str:
    return _build("f1", "edate", watch_id, mode)


def find_any(watch_id: int) -> str:
    return _build("f1", "any", watch_id)


def find_cancel() -> str:
    return _build("f1", "x")


# w1: my watches


def watches_list() -> str:
    return _build("w1", "list")


def watch_pause(watch_id: int) -> str:
    return _build("w1", "pause", watch_id)


def watch_resume(watch_id: int) -> str:
    return _build("w1", "resume", watch_id)


def watch_stop(watch_id: int) -> str:
    return _build("w1", "stop", watch_id)


def watch_stop_yes(watch_id: int) -> str:
    return _build("w1", "stopy", watch_id)


def watch_stop_no(watch_id: int) -> str:
    return _build("w1", "stopn", watch_id)


# s1: settings


def settings_home() -> str:
    return _build("s1", "home")


def settings_forget() -> str:
    return _build("s1", "forget")


def settings_delete() -> str:
    return _build("s1", "del")


def settings_delete_yes() -> str:
    return _build("s1", "dely")


def settings_delete_no() -> str:
    return _build("s1", "deln")


# b1: booking


def book_day(watch_id: int, day: date) -> str:
    return _build("b1", watch_id, day.strftime("%Y%m%d"))


def book_time(office_id: int, ts: int) -> str:
    return _build("b1", "t", office_id, ts)


def book_me() -> str:
    return _build("b1", "me")


def book_change() -> str:
    return _build("b1", "chg")


def book_ok() -> str:
    return _build("b1", "ok")


def book_cancel() -> str:
    return _build("b1", "x")


# parsing

_ID = re.compile(r"\d{1,10}")
_CATEGORY = re.compile(r"[a-z_]{1,40}")

# action -> argument kinds; "id" = non-negative int, other kinds are listed values
_SCHEMES: dict[str, dict[str, tuple]] = {
    "f1": {
        "home": (),
        "all": (),
        "cat": ("category", "id"),
        "svc": ("id",),
        "off": ("id", "id"),
        "when": ("id", "id", WHEN_PRESETS),
        "date": ("id", "id", DATE_MODES),
        "edit": ("id",),
        "ewhen": ("id", WHEN_PRESETS),
        "edate": ("id", DATE_MODES),
        "any": ("id",),
        "x": (),
    },
    "w1": {
        "list": (),
        "pause": ("id",),
        "resume": ("id",),
        "stop": ("id",),
        "stopy": ("id",),
        "stopn": ("id",),
    },
    "s1": {"home": (), "forget": (), "del": (), "dely": (), "deln": ()},
    "b1": {"t": ("id", "id"), "me": (), "chg": (), "ok": (), "x": ()},
}


def _arg(kind, raw: str):
    if kind == "id":
        return int(raw) if _ID.fullmatch(raw) else None
    if kind == "category":
        return raw if _CATEGORY.fullmatch(raw) else None
    return raw if raw in kind else None


def _parse_book_day(parts: list[str]) -> Cb | None:
    if (
        len(parts) != 3
        or not _ID.fullmatch(parts[1])
        or not re.fullmatch(r"\d{8}", parts[2])
    ):
        return None
    try:
        day = datetime.strptime(parts[2], "%Y%m%d").date()
    except ValueError:
        return None
    return Cb("b1", "day", (int(parts[1]), day))


def parse(data: str) -> Cb | None:
    """Cb for data built by this module, or None for anything else."""
    parts = (data or "").split(":")
    scope = parts[0]
    if scope not in _SCHEMES or len(parts) < 2:
        return None
    if scope == "b1" and parts[1].isdigit():
        return _parse_book_day(parts)
    action, raw_args = parts[1], parts[2:]
    kinds = _SCHEMES[scope].get(action)
    if kinds is None or len(raw_args) != len(kinds):
        return None
    args = tuple(_arg(kind, raw) for kind, raw in zip(kinds, raw_args))
    if any(a is None for a in args):
        return None
    return Cb(scope, action, args)
