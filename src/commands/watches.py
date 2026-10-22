# ABOUTME: My watches screen: one line per watch with its state and buttons to change, pause or stop.
# ABOUTME: Entry points for /watches, its alias commands and every "w1:" button.

import html
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.handlers import text_input
from src.handlers.language_picker import client_language
from src.i18n import t
from src.i18n.user_language import get_stored_language, get_user_language
from src.repositories import (
    MAX_OPEN_WATCHES,
    PendingRetireRepository,
    UserRepository,
    WatchRecord,
    WatchRepository,
)
from src.services.analytics_service import track_event
from src.ui import callbacks as cb
from src.ui.screens import show_screen
from src.ui.telegram_safe import (
    EditOutcome,
    safe_answer,
    safe_edit_text,
    safe_send,
    safe_strip_markup,
)
from src.watches import when
from src.watches.alert_ops import alert_lock, close_live_alert
from src.watches.alert_view import FinalState, render_alert
from src.watches.availability import public_office_ids
from src.watches.labels import ago_label, watch_state, watch_summary

logger = logging.getLogger(__name__)

RECENT_ENDED = timedelta(days=7)
MAX_RECENT_ENDED = 3


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _checked(rec: WatchRecord, lang: str, now: datetime) -> str:
    if rec.status != "active" or rec.last_checked_at is None:
        return ""
    return t("watches.checked", lang, ago=ago_label(now - rec.last_checked_at, lang))


def _line(rec: WatchRecord, n: int, lang: str, now: datetime) -> str:
    return t(
        "watches.line",
        lang,
        n=n,
        summary=html.escape(watch_summary(rec, lang)),
        state=watch_state(rec, lang),
        checked=_checked(rec, lang, now),
    )


def _row(rec: WatchRecord, n: int, lang: str) -> list[InlineKeyboardButton]:
    if not rec.is_open and rec.end_reason == "gone":
        # Same follow-up as the S17g alert; the watch's office can no longer be searched
        if not public_office_ids(rec.service_id):
            return []
        return [_button(t("watches.btn_any_office", lang, n=n), cb.find_any(rec.id))]
    if not rec.is_open:
        return [_button(t("watches.btn_again", lang, n=n), cb.find_edit(rec.id))]
    if rec.status == "paused":
        toggle = _button(t("watches.btn_resume", lang), cb.watch_resume(rec.id))
    else:
        toggle = _button(t("watches.btn_pause", lang), cb.watch_pause(rec.id))
    return [
        _button(t("watches.btn_time", lang, n=n), cb.find_edit(rec.id)),
        toggle,
        _button(t("watches.btn_stop", lang), cb.watch_stop(rec.id)),
    ]


def build_watches_screen(
    user_id: int, lang: str, now: datetime
) -> tuple[str, InlineKeyboardMarkup]:
    """Open watches first, then up to three booked/deadline/gone ones of the last 7 days"""
    with get_session() as session:
        records = WatchRepository(session).list_for_user(user_id, now - RECENT_ENDED)
    open_watches = [r for r in records if r.is_open]
    ended = [r for r in records if not r.is_open][:MAX_RECENT_ENDED]
    if not open_watches and not ended:
        find = _button(t("watches.btn_find", lang), cb.find_home())
        return t("watches.empty", lang), InlineKeyboardMarkup([[find]])

    shown = list(enumerate(open_watches + ended, 1))
    if len(open_watches) > MAX_OPEN_WATCHES:
        header = t("watches.header_over", lang, count=len(open_watches))
    else:
        header = t(
            "watches.header", lang, count=len(open_watches), limit=MAX_OPEN_WATCHES
        )
    lines = [header] + [_line(rec, n, lang, now) for n, rec in shown]
    rows = [row for n, rec in shown if (row := _row(rec, n, lang))]
    if len(open_watches) < MAX_OPEN_WATCHES:
        rows.append([_button(t("watches.btn_new", lang), cb.find_home())])
    return "\n\n".join(lines), InlineKeyboardMarkup(rows)


async def _show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    text, markup = build_watches_screen(user_id, lang, when.utcnow())
    await show_screen(update, context, text, markup)


async def watches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watches, /myservices, /status, /setdates and the reply keyboard's My watches button"""
    text_input.clear_pending_input(context)
    user_id = update.effective_user.id
    if get_stored_language(user_id) is None:
        await safe_send(
            context.bot,
            update.effective_chat.id,
            t("start.not_registered", client_language(update)),
        )
        return
    await _show_list(update, context)


def _pressed_id(update: Update) -> int | None:
    message = update.callback_query.message
    return None if message is None else message.message_id


def _is_live_alert(rec: WatchRecord, update: Update) -> bool:
    return (
        rec.live is not None
        and rec.live.chat_id == update.effective_chat.id
        and rec.live.message_id == _pressed_id(update)
    )


def _summary(rec: WatchRecord, lang: str) -> str:
    return html.escape(watch_summary(rec, lang))


def _reread(watch_id: int, user_id: int) -> WatchRecord | None:
    with get_session() as session:
        return WatchRepository(session).get_for_user(watch_id, user_id)


def _set_status(watch_id: int, status: str, **reasons: str) -> None:
    with get_session() as session:
        WatchRepository(session).set_status(watch_id, status, **reasons)


async def _pause(update, context, rec: WatchRecord, lang: str) -> None:
    async with alert_lock(rec.id):
        current = _reread(rec.id, rec.user_id)
        if current is not None and current.status == "active":
            _set_status(rec.id, "paused", pause_reason="user")
            await close_live_alert(
                context.bot, rec.id, FinalState.PAUSED, lang, by_user=True
            )
            await track_event(
                "watch_paused", user_id=rec.user_id, service_id=rec.service_id
            )
    await _show_list(update, context)


async def _resume(update, context, rec: WatchRecord, lang: str) -> None:
    async with alert_lock(rec.id):
        current = _reread(rec.id, rec.user_id)
        if current is not None and current.status == "paused":
            _set_status(rec.id, "active")
            await track_event(
                "watch_resumed", user_id=rec.user_id, service_id=rec.service_id
            )
    await _show_list(update, context)


async def _ask_stop(update, context, rec: WatchRecord, lang: str) -> None:
    text = t("watches.stop_confirm", lang, summary=_summary(rec, lang))
    markup = InlineKeyboardMarkup(
        [
            [
                _button(t("watches.btn_stop_yes", lang), cb.watch_stop_yes(rec.id)),
                _button(t("watches.btn_stop_no", lang), cb.watch_stop_no(rec.id)),
            ]
        ]
    )
    if _is_live_alert(rec, update):
        await safe_edit_text(
            context.bot, update.effective_chat.id, _pressed_id(update), text, markup
        )
    else:
        await show_screen(update, context, text, markup)


async def _stop(update, context, rec: WatchRecord, lang: str) -> None:
    on_alert = _is_live_alert(rec, update)
    async with alert_lock(rec.id):
        current = _reread(rec.id, rec.user_id)
        if current is not None and current.is_open:
            _set_status(rec.id, "ended", end_reason="stopped")
            await close_live_alert(
                context.bot, rec.id, FinalState.STOPPED, lang, by_user=True
            )
            await track_event(
                "watch_stopped", user_id=rec.user_id, service_id=rec.service_id
            )
    if not on_alert:
        await _show_list(update, context)


async def _keep(update, context, rec: WatchRecord, lang: str) -> None:
    if not _is_live_alert(rec, update) or rec.snapshot is None:
        await _show_list(update, context)
        return
    async with alert_lock(rec.id):
        current = _reread(rec.id, rec.user_id)
        if current is None or current.snapshot is None:
            return
        snapshot = current.snapshot
        rendered = render_alert(current, snapshot, lang, initial=False)
        outcome = await safe_edit_text(
            context.bot,
            update.effective_chat.id,
            _pressed_id(update),
            rendered.text,
            rendered.markup,
        )
        if outcome in (EditOutcome.OK, EditOutcome.NOT_MODIFIED) and _is_live_alert(
            current, update
        ):
            with get_session() as session:
                WatchRepository(session).update_live_alert(
                    rec.id,
                    rendered.kind,
                    snapshot.slots,
                    current.alerted | snapshot.slots,
                    rendered.render_hash,
                )


_ACTIONS = {
    "pause": _pause,
    "resume": _resume,
    "stop": _ask_stop,
    "stopy": _stop,
    "stopn": _keep,
}


async def _stale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A button of a watch that is gone or already ended"""
    pressed = _pressed_id(update)
    with get_session() as session:
        nav = UserRepository(session).get_nav_message_id(update.effective_user.id)
    if pressed is not None and pressed == nav:
        await _show_list(update, context)
    elif pressed is not None:
        await safe_strip_markup(context.bot, update.effective_chat.id, pressed)


async def watches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "w1:" button"""
    query = update.callback_query
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    text_input.clear_pending_input(context)

    parsed = cb.parse(query.data)
    if parsed is None or parsed.action not in _ACTIONS:
        await safe_answer(query)
        await _show_list(update, context)
        return

    rec = _reread(parsed.args[0], user_id)
    if rec is None or not rec.is_open:
        await safe_answer(query, t("watches.not_open", lang))
        await _stale(update, context)
        return
    await safe_answer(query)
    pressed = _pressed_id(update)
    if pressed is not None and not _is_live_alert(rec, update):
        # The pressed message gets new content, so a final text queued for it no longer applies
        with get_session() as session:
            PendingRetireRepository(session).discard(update.effective_chat.id, pressed)
    await _ACTIONS[parsed.action](update, context, rec, lang)
