# ABOUTME: Slot identity (day, office), watch snapshots and their JSON form, calendar filtering.
# ABOUTME: Pure functions over the city's available-calendar response.

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import NamedTuple

from src.watches.when import Window

BOOK_BUTTON_DAYS = 3


class Slot(NamedTuple):
    day: date
    office_id: int


class SlotTime(NamedTuple):
    ts: int
    office_id: int


@dataclass(frozen=True)
class WatchSnapshot:
    checked_at: datetime  # naive UTC
    ok: bool  # False: query failed, nothing else is meaningful
    slots: frozenset[Slot] = frozenset()
    earliest_times: tuple[
        SlotTime, ...
    ] = ()  # all times of the earliest day, sorted by ts

    @property
    def earliest_day(self) -> date | None:
        return min((s.day for s in self.slots), default=None)

    def days(self) -> list[date]:
        return sorted({s.day for s in self.slots})


def slot_key(s: Slot) -> str:
    return f"{s.day.isoformat()}@{s.office_id}"


def parse_slot_key(k: str) -> Slot:
    if not isinstance(k, str):
        raise TypeError(f"Invalid slot key: {k!r}")
    day, sep, office = k.partition("@")
    if not sep:
        raise ValueError(f"Invalid slot key: {k!r}")
    return Slot(date.fromisoformat(day), int(office))


def encode_slots(s: frozenset[Slot]) -> str:
    return json.dumps(sorted(slot_key(slot) for slot in s))


def decode_slots(raw: str) -> frozenset[Slot]:
    keys = json.loads(raw)
    if not isinstance(keys, list):
        raise TypeError(f"Slot list expected, got {type(keys).__name__}")
    return frozenset(parse_slot_key(k) for k in keys)


def snapshot_to_json(s: WatchSnapshot) -> str:
    return json.dumps(
        {
            "checked_at": s.checked_at.isoformat(),
            "ok": s.ok,
            "slots": sorted(slot_key(slot) for slot in s.slots),
            "earliest_times": [[t.ts, t.office_id] for t in s.earliest_times],
        }
    )


def snapshot_from_json(raw: str | None) -> WatchSnapshot | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return WatchSnapshot(
            checked_at=datetime.fromisoformat(data["checked_at"]),
            ok=bool(data["ok"]),
            slots=frozenset(parse_slot_key(k) for k in data["slots"]),
            earliest_times=tuple(
                SlotTime(int(ts), int(o)) for ts, o in data["earliest_times"]
            ),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid snapshot: {exc}") from exc


def top_days(slots: frozenset[Slot], n: int = BOOK_BUTTON_DAYS) -> frozenset[date]:
    return frozenset(sorted({s.day for s in slots})[:n])


def prune_past(slots: frozenset[Slot], today: date) -> frozenset[Slot]:
    return frozenset(s for s in slots if s.day >= today)


def _provider_ids(entry: dict) -> set[int]:
    raw = entry.get("providerIDs") or ""
    return {int(part) for part in str(raw).split(",") if part.strip()}


def _days(calendar: dict) -> list[dict]:
    return calendar.get("availableDays") or []


def slots_in_scope(
    calendar: dict, office_ids: set[int], window: Window
) -> frozenset[Slot]:
    slots = set()
    for entry in _days(calendar):
        day = date.fromisoformat(entry["date"])
        if window.start <= day <= window.end:
            slots.update(Slot(day, o) for o in _provider_ids(entry) & office_ids)
    return frozenset(slots)


def calendar_times(
    calendar: dict, day: date, office_ids: set[int]
) -> tuple[SlotTime, ...] | None:
    """Times of `day` for `office_ids`, or None unless every relevant provider office carries them."""
    entry = next((e for e in _days(calendar) if e.get("date") == day.isoformat()), None)
    if entry is None:
        return None
    relevant = _provider_ids(entry) & office_ids
    by_office = {
        int(o["officeId"]): o.get("appointments") or []
        for o in entry.get("offices") or []
        if int(o["officeId"]) in relevant
    }
    if any(not by_office.get(o) for o in relevant):
        return None
    return tuple(
        sorted(SlotTime(int(ts), o) for o, stamps in by_office.items() for ts in stamps)
    )


def times_for_offices(
    times: tuple[SlotTime, ...], office_ids: set[int]
) -> tuple[SlotTime, ...]:
    return tuple(t for t in times if t.office_id in office_ids)
