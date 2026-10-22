# ABOUTME: Renders a watch's alert message (text, buttons, kind, content hash) for each lifecycle state.
# ABOUTME: City names are HTML-escaped here; texts come from the "alert" catalog area.

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import groupby
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.config import get_config
from src.i18n import t
from src.ui import callbacks as cb
from src.watches.availability import public_office_ids
from src.watches.labels import (
    day_label,
    office_label,
    only_office,
    short_date_label,
    watch_summary,
)
from src.watches.slots import SlotTime, WatchSnapshot, top_days

BERLIN = ZoneInfo("Europe/Berlin")
MAX_TIMES = 5
LISTED_OTHER_DAYS = 2


class FinalState(StrEnum):
    BOOKED = "booked"
    STOPPED = "stopped"
    PAUSED = "paused"
    DEADLINE = "deadline"
    GONE = "gone"
    OUTDATED = "outdated"


@dataclass(frozen=True)
class RenderedAlert:
    text: str
    markup: InlineKeyboardMarkup | None
    kind: str  # "slots" | "empty" | "ended"
    render_hash: str


def _hash(text: str, markup: InlineKeyboardMarkup | None) -> str:
    markup_json = json.dumps(markup.to_dict() if markup else None, sort_keys=True)
    return hashlib.sha1((text + markup_json).encode()).hexdigest()


def _rendered(
    text: str, markup: InlineKeyboardMarkup | None, kind: str
) -> RenderedAlert:
    return RenderedAlert(text, markup, kind, _hash(text, markup))


def _summary(rec, lang: str) -> str:
    return html.escape(watch_summary(rec, lang))


def _clock_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=BERLIN).strftime("%H:%M")


def _times_text(rec, times: tuple[SlotTime, ...], lang: str) -> str:
    shown = times[:MAX_TIMES]
    if not shown:
        return t("alert.times_unknown", lang)
    if rec.office_id is not None or only_office(rec.service_id) is not None:
        return ", ".join(_clock_time(s.ts) for s in shown)
    parts = []
    for office, run in groupby(
        shown, key=lambda s: office_label(s.office_id, rec.service_id, lang)
    ):
        clocks = [_clock_time(s.ts) for s in run]
        clocks[-1] = f"{clocks[-1]} ({html.escape(office)})"
        parts.extend(clocks)
    return ", ".join(parts)


def _more_text(days: list, lang: str) -> str:
    others = days[1:]
    if not others:
        return ""
    listed = ", ".join(short_date_label(d) for d in others[:LISTED_OTHER_DAYS])
    rest = len(others) - LISTED_OTHER_DAYS
    if rest > 0:
        return "\n" + t("alert.also_free_more", lang, days=listed, count=rest)
    return "\n" + t("alert.also_free", lang, days=listed)


def _website_office(rec, snapshot: WatchSnapshot) -> int:
    if snapshot.earliest_times:
        return snapshot.earliest_times[0].office_id
    if rec.office_id is not None:
        return rec.office_id
    earliest = snapshot.earliest_day
    return min(s.office_id for s in snapshot.slots if s.day == earliest)


def _slots_markup(rec, snapshot: WatchSnapshot, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                t("alert.btn_book", lang, day=day_label(day, lang)),
                callback_data=cb.book_day(rec.id, day),
            )
        ]
        for day in sorted(top_days(snapshot.slots))
    ]
    url = get_config().get_booking_url_for_service(
        rec.service_id, _website_office(rec, snapshot)
    )
    rows.append(
        [
            InlineKeyboardButton(t("alert.btn_website", lang), url=url),
            InlineKeyboardButton(
                t("alert.btn_stop", lang), callback_data=cb.watch_stop(rec.id)
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


def render_alert(
    rec,
    snapshot: WatchSnapshot,
    lang: str,
    *,
    initial: bool,
    updated_existing: bool = False,
) -> RenderedAlert:
    """S12 for slots. Without slots: S13/S13f for the first check after creating or changing
    the watch (initial=True); the checker's empty state (S14) otherwise."""
    summary = _summary(rec, lang)
    if not snapshot.ok:
        text, markup, kind = (
            t("alert.check_failed", lang, summary=summary),
            None,
            "empty",
        )
    elif not snapshot.slots:
        if not initial:
            return render_empty_now(rec, snapshot.checked_at, lang)
        text, markup, kind = t("alert.none_yet", lang, summary=summary), None, "empty"
    else:
        days = snapshot.days()
        text = t(
            "alert.slots",
            lang,
            summary=summary,
            day=day_label(days[0], lang),
            times=_times_text(rec, snapshot.earliest_times, lang),
            more=_more_text(days, lang),
        )
        markup, kind = _slots_markup(rec, snapshot, lang), "slots"
    if updated_existing:
        text = f"{t('alert.updated_existing', lang)}\n\n{text}"
    return _rendered(text, markup, kind)


def render_empty_now(rec, as_of: datetime, lang: str) -> RenderedAlert:
    """S14; `as_of` is naive UTC."""
    local = as_of.replace(tzinfo=UTC).astimezone(BERLIN).strftime("%H:%M")
    text = t("alert.empty_now", lang, summary=_summary(rec, lang), time=local)
    return _rendered(text, None, "empty")


def render_outdated(lang: str) -> str:
    return t("alert.outdated", lang)


def render_final(rec, final: FinalState, lang: str) -> str:
    if final is FinalState.OUTDATED:
        return render_outdated(lang)
    return t(f"alert.final_{final.value}", lang, summary=_summary(rec, lang))


def render_ended(rec, lang: str) -> RenderedAlert:
    """S17 (deadline passed) or S17g (office or service gone) with their follow-up buttons."""
    new_search = InlineKeyboardButton(
        t("alert.btn_new_search", lang), callback_data=cb.find_home()
    )
    if rec.end_reason == "gone":
        text = t("alert.gone", lang, summary=_summary(rec, lang))
        row = [new_search]
        if public_office_ids(rec.service_id):
            row.insert(
                0,
                InlineKeyboardButton(
                    t("alert.btn_any_office", lang), callback_data=cb.find_any(rec.id)
                ),
            )
    else:
        text = t("alert.deadline", lang, summary=_summary(rec, lang))
        row = [
            InlineKeyboardButton(
                t("alert.btn_extend", lang), callback_data=cb.find_edit(rec.id)
            ),
            new_search,
        ]
    return _rendered(text, InlineKeyboardMarkup([row]), "ended")


def render_booking_timed_out(lang: str) -> str:
    return t("alert.booking_timed_out", lang)
