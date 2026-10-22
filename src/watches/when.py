# ABOUTME: "When" part of a watch: presets, typed date parsing and validation, search windows.
# ABOUTME: Pure functions; "today" is always passed in (Europe/Berlin calendar date).

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
ASAP_HORIZON_DAYS = 180
# The API rejects ranges of ~400 days; 364 keeps every query safely inside
MAX_QUERY_DAYS = 364

WhenKind = Literal["asap", "within", "before", "between"]


@dataclass(frozen=True)
class WhenSpec:
    kind: WhenKind
    within_days: int | None = None
    date_from: date | None = None
    # "before": exclusive deadline; "between": inclusive end
    date_to: date | None = None


@dataclass(frozen=True)
class Window:
    start: date
    end: date  # inclusive


class DateError(StrEnum):
    FORMAT = "format"
    PAST = "past"
    TOO_FAR = "too_far"
    ORDER = "order"


PRESETS: dict[str, WhenSpec] = {
    "asap": WhenSpec("asap"),
    "2w": WhenSpec("within", 14),
    "1m": WhenSpec("within", 30),
    "3m": WhenSpec("within", 90),
}

DATE_TOKEN = r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}(?:\.\d{2,4})?"
_DATE_TOKEN_RE = re.compile(DATE_TOKEN)
_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DOTTED_RE = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?")


def today_berlin() -> date:
    return datetime.now(BERLIN).date()


def utcnow() -> datetime:
    """Current time as naive UTC (the DB convention); one place for tests to fix the clock."""
    return datetime.now(UTC).replace(tzinfo=None)


def _max_end(today: date) -> date:
    return today + timedelta(days=MAX_QUERY_DAYS)


def effective_window(spec: WhenSpec, today: date) -> Window | None:
    """Search window for spec on today; None once a before/between watch has passed."""
    limit = _max_end(today)
    if spec.kind == "asap":
        return Window(today, min(today + timedelta(days=ASAP_HORIZON_DAYS), limit))
    if spec.kind == "within":
        return Window(today, min(today + timedelta(days=spec.within_days or 0), limit))
    if spec.kind == "before":
        if spec.date_to is None or today >= spec.date_to:
            return None
        return Window(today, min(spec.date_to - timedelta(days=1), limit))
    if spec.kind == "between":
        if spec.date_from is None or spec.date_to is None or today > spec.date_to:
            return None
        return Window(max(spec.date_from, today), min(spec.date_to, limit))
    raise ValueError(f"Unknown when kind: {spec.kind!r}")


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_user_date(text: str, today: date) -> date | None:
    """Parse one typed date: ISO (padding optional), D.M.YYYY, D.M.YY or D.M (next occurrence)."""
    token = text.strip()
    if match := _ISO_RE.fullmatch(token):
        return _safe_date(*(int(part) for part in match.groups()))
    match = _DOTTED_RE.fullmatch(token)
    if match is None:
        return None
    day, month, year = match.groups()
    if year is not None:
        full_year = int(year) + 2000 if len(year) == 2 else int(year)
        return _safe_date(full_year, int(month), int(day))
    for candidate_year in range(today.year, today.year + 9):
        candidate = _safe_date(candidate_year, int(month), int(day))
        if candidate is not None and candidate > today:
            return candidate
    return None


def parse_date_range(text: str, today: date) -> tuple[date, date] | None:
    """Exactly two date tokens anywhere in the text; anything between them is ignored."""
    tokens = _DATE_TOKEN_RE.findall(text)
    if len(tokens) != 2:
        return None
    first, second = (parse_user_date(token, today) for token in tokens)
    if first is None or second is None:
        return None
    return first, second


def validate_before(d: date, today: date) -> DateError | None:
    if d <= today:
        return DateError.PAST
    if d > _max_end(today):
        return DateError.TOO_FAR
    return None


def validate_between(a: date, b: date, today: date) -> DateError | None:
    if a > b:
        return DateError.ORDER
    if b < today:
        return DateError.PAST
    if b > _max_end(today):
        return DateError.TOO_FAR
    return None


def _parse_stored_iso(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def migrated_when(start_raw: str | None, end_raw: str | None, today: date) -> WhenSpec:
    """WhenSpec for a user's stored global date range (migration v2)."""
    start = _parse_stored_iso(start_raw)
    end = _parse_stored_iso(end_raw)
    if start is None or end is None or start > end or start > _max_end(today):
        return WhenSpec("asap")
    # Signup default and the "6 months" preset both stored exactly this span
    if (end - start).days == ASAP_HORIZON_DAYS:
        return WhenSpec("asap")
    error = validate_between(start, end, today)
    if error is DateError.PAST:
        return WhenSpec("asap")
    if error is DateError.TOO_FAR:
        end = _max_end(today)
    return WhenSpec("between", date_from=start, date_to=end)
