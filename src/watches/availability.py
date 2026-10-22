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
    OTHER = "other"


@dataclass(frozen=True)
class CallResult:
    ok: bool
    data: dict | None
    error: ApiError | None


def public_office_ids(service_id: int) -> set[int]:
    """Offices with a public relation to the service that exist in the catalog."""
    payload = services_manager.get_full_payload()
    known = {office["id"] for office in payload.get("offices", [])}
    return {
        r["officeId"]
        for r in payload.get("relations", [])
        if r["serviceId"] == service_id
        and r.get("public", True)
        and r["officeId"] in known
    }


def watch_office_ids(rec) -> list[int]:
    """The watch's office, or every public office of its service."""
    if rec.office_id is not None:
        return [rec.office_id]
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
            return CallResult(False, None, ApiError.OTHER)
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
        return CallResult(False, None, ApiError.OTHER)
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
    service_id: int, office_ids: list[int], start: date, end: date
) -> tuple[CallResult, set[int]]:
    """fetch_calendar; on a combination error query each office alone and merge the results.
    Returns the result and the offices dropped for failing with a combination error."""
    result = await fetch_calendar(service_id, office_ids, start, end)
    if result.error is not ApiError.COMBINATION:
        return result, set()

    calendars, dropped = [], set()
    for office_id in office_ids:
        single = await fetch_calendar(service_id, [office_id], start, end)
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
    result = await fetch_calendar(service_id, office_ids, day, day, slots_day=day)
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
    if window is None or not offices:
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
