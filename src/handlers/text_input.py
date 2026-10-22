# ABOUTME: Plain text messages: a typed date answer when one is awaited, otherwise a service search.
# ABOUTME: The awaited answer lives in context.user_data[AWAIT_KEY].

import html
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src import services_manager
from src.database import get_session
from src.handlers.language_picker import client_language
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import UserRepository
from src.services.immediate_check import start_recheck, start_watch_check
from src.services.service_search import MAX_QUERY_CHARS, search_services
from src.ui import callbacks as cb
from src.ui.screens import show_screen
from src.ui.telegram_safe import safe_send
from src.watches import when as when_module
from src.watches.labels import date_label, service_label
from src.watches.when import (
    MAX_QUERY_DAYS,
    DateError,
    WhenSpec,
    parse_date_range,
    parse_user_date,
    validate_before,
    validate_between,
)

AWAIT_KEY = "await_date"

DATE_ERROR_KEYS = {
    DateError.FORMAT: "find.date_format",
    DateError.PAST: "find.date_past",
    DateError.TOO_FAR: "find.date_too_far",
    DateError.ORDER: "find.date_order",
}


def clear_pending_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAIT_KEY, None)


def cancel_markup(lang: str) -> InlineKeyboardMarkup:
    """The typed-date prompt's only button"""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("find.btn_cancel", lang), callback_data=cb.find_cancel()
                )
            ]
        ]
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    pending = context.user_data.get(AWAIT_KEY)
    if pending is not None:
        if any(char.isdigit() for char in text):
            await _answer_date(update, context, pending, text)
            return
        clear_pending_input(context)
    await _search(update, context, text)


async def _search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    with get_session() as session:
        registered = UserRepository(session).get_user(user_id) is not None
    if not registered:
        await safe_send(
            context.bot,
            update.effective_chat.id,
            t("start.not_registered", client_language(update)),
        )
        return

    query = text.strip()[:MAX_QUERY_CHARS]
    results = search_services(query, services_manager.get_services())
    rows = [
        [
            InlineKeyboardButton(
                service_label(s["id"], lang), callback_data=cb.find_service(s["id"])
            )
        ]
        for s in results
    ]
    rows.append(
        [InlineKeyboardButton(t("find.btn_all", lang), callback_data=cb.find_all())]
    )
    key = "find.results" if results else "find.nothing"
    await show_screen(
        update,
        context,
        t(key, lang, query=html.escape(query)),
        InlineKeyboardMarkup(rows),
    )


def _parse_answer(
    kind: str, text: str, today
) -> tuple[WhenSpec | None, DateError | None]:
    if kind == "before":
        day = parse_user_date(text, today)
        if day is None:
            return None, DateError.FORMAT
        return WhenSpec("before", date_to=day), validate_before(day, today)
    pair = parse_date_range(text, today)
    if pair is None:
        return None, DateError.FORMAT
    start, end = pair
    return (
        WhenSpec("between", date_from=start, date_to=end),
        validate_between(start, end, today),
    )


async def _answer_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str
) -> None:
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    today = when_module.today_berlin()
    spec, error = _parse_answer(pending["kind"], text, today)
    if error is not None:
        max_date = date_label(today + timedelta(days=MAX_QUERY_DAYS))
        message = await show_screen(
            update,
            context,
            t(DATE_ERROR_KEYS[error], lang, max_date=max_date),
            cancel_markup(lang),
        )
        if message is not None:
            pending["prompt_msg_id"] = message.message_id
        return

    clear_pending_input(context)
    if pending.get("watch_id") is not None:
        await start_recheck(
            update, context, pending["watch_id"], spec, target_message_id=None
        )
    else:
        await start_watch_check(
            update,
            context,
            user_id,
            pending["service_id"],
            pending["office_id"],
            spec,
            target_message_id=None,
        )
