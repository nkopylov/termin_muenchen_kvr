# ABOUTME: Checks a watch right after it is created or changed and shows the result as its live alert.
# ABOUTME: The handler returns at once; the network part runs as a per-user background task.

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import (
    MAX_OPEN_WATCHES,
    LimitReached,
    UserRepository,
    WatchRepository,
)
from src.services.analytics_service import track_event
from src.ui import callbacks as cb
from src.ui.background import run_for_user
from src.ui.screens import forget_nav_message, retire_nav_message
from src.ui.telegram_safe import EditOutcome, safe_edit_text, safe_send
from src.watches import availability
from src.watches import when as when_module
from src.watches.alert_ops import (
    alert_lock,
    close_live_alert,
    running_immediate_check,
)
from src.watches.alert_view import FinalState, render_alert, render_final
from src.watches.labels import service_label
from src.watches.when import WhenSpec

# user_data key: id of the message whose check is running (double tap guard)
CHECKING_KEY = "checking"

_SHOWN = (EditOutcome.OK, EditOutcome.NOT_MODIFIED)


def build_limit_screen(lang: str, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """S10: the user already has the maximum number of open watches (or more: migrated
    users keep all their subscriptions)."""
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("keyboard.watches", lang), callback_data=cb.watches_list()
                )
            ]
        ]
    )
    with get_session() as session:
        open_count = WatchRepository(session).count_open(user_id)
    if open_count > MAX_OPEN_WATCHES:
        text = t(
            "find.limit_over",
            lang,
            open=open_count,
            limit=MAX_OPEN_WATCHES,
            count=open_count - MAX_OPEN_WATCHES + 1,
        )
    else:
        text = t("find.limit", lang, count=MAX_OPEN_WATCHES)
    return text, markup


async def _show_checking(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    service_id: int,
    target_message_id: int | None,
    lang: str,
) -> int | None:
    """S11 on the target message, or on a new message; returns the message id."""
    bot = context.bot
    chat_id = update.effective_chat.id
    text = t(
        "find.checking", lang, service=html.escape(service_label(service_id, lang))
    )
    if target_message_id is not None:
        outcome = await safe_edit_text(bot, chat_id, target_message_id, text)
        if outcome in _SHOWN:
            # Before the alert gets buttons, so no later nav screen strips them
            forget_nav_message(user_id, target_message_id)
            return target_message_id
    message, _ = await safe_send(bot, chat_id, text)
    if message is None:
        return None
    # The typed-date prompt (the current nav screen) is answered now
    await retire_nav_message(bot, user_id)
    return message.message_id


async def _show_limit(
    bot, user_id: int, chat_id: int, message_id: int, lang: str
) -> None:
    """S10 on the checking message; it becomes the nav screen unless a newer one exists."""
    text, markup = build_limit_screen(lang, user_id)
    outcome = await safe_edit_text(bot, chat_id, message_id, text, markup)
    if outcome not in _SHOWN:
        return
    with get_session() as session:
        users = UserRepository(session)
        if users.get_nav_message_id(user_id) is None:
            users.set_nav_message_id(user_id, message_id)


async def _detach_other_alerts(
    user_id: int, chat_id: int, message_id: int, watch_id: int
) -> None:
    """Other watches whose live alert is this message lose it; the message is not edited."""

    def points_here(rec) -> bool:
        return rec is not None and (
            rec.live is not None
            and (rec.live.chat_id, rec.live.message_id) == (chat_id, message_id)
        )

    with get_session() as session:
        others = [
            rec.id
            for rec in WatchRepository(session).list_for_user(user_id, None)
            if rec.id != watch_id and points_here(rec)
        ]
    for other_id in others:
        async with alert_lock(other_id):
            with get_session() as session:
                watches = WatchRepository(session)
                if points_here(watches.get(other_id)):
                    watches.clear_live_alert(other_id, reset_alerted=False)


def _final_state(rec) -> FinalState:
    if rec.status == "paused":
        return FinalState.PAUSED
    if rec.end_reason in {state.value for state in FinalState}:
        return FinalState(rec.end_reason)
    return FinalState.STOPPED


async def _check_and_show(
    bot,
    user_id: int,
    chat_id: int,
    message_id: int,
    watch_id: int,
    updated: bool,
    lang: str,
) -> None:
    """Check the watch and make `message_id` its live alert. alert_lock is taken only after
    the city answered, so taps on the watch's messages never wait for the network."""
    with get_session() as session:
        rec = WatchRepository(session).get(watch_id)
    if rec is None:
        return
    snapshot = await availability.snapshot_for_watch(rec, when_module.today_berlin())

    async with alert_lock(watch_id):
        with get_session() as session:
            rec = WatchRepository(session).get(watch_id)
        if rec is None:
            return
        if rec.status != "active":
            # Paused or stopped while the city was queried
            text = render_final(rec, _final_state(rec), lang)
            await safe_edit_text(bot, chat_id, message_id, text)
            return
        if rec.live is not None and (rec.live.chat_id, rec.live.message_id) != (
            chat_id,
            message_id,
        ):
            await close_live_alert(
                bot, watch_id, FinalState.OUTDATED, lang, by_user=True
            )

        with get_session() as session:
            WatchRepository(session).record_check(watch_id, snapshot)
        rendered = render_alert(
            rec, snapshot, lang, initial=True, updated_existing=updated
        )
        await _detach_other_alerts(user_id, chat_id, message_id, watch_id)
        outcome = await safe_edit_text(
            bot, chat_id, message_id, rendered.text, rendered.markup
        )
        with get_session() as session:
            watches = WatchRepository(session)
            if outcome in _SHOWN:
                watches.set_live_alert(
                    watch_id,
                    chat_id,
                    message_id,
                    rendered.kind,
                    snapshot.slots,
                    snapshot.slots,
                    rendered.render_hash,
                )
            else:
                watches.clear_live_alert(watch_id, reset_alerted=True)
                if outcome is EditOutcome.FORBIDDEN:
                    watches.pause_all_for_user(user_id, reason="blocked")


def _clear_checking(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    if context.user_data.get(CHECKING_KEY) == message_id:
        context.user_data.pop(CHECKING_KEY, None)


async def start_watch_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    service_id: int,
    office_id: int | None,
    when: WhenSpec,
    *,
    target_message_id: int | None,
) -> None:
    lang = get_user_language(user_id, context)
    message_id = await _show_checking(
        update, context, user_id, service_id, target_message_id, lang
    )
    if message_id is None:
        return
    context.user_data[CHECKING_KEY] = message_id
    chat_id = update.effective_chat.id
    bot = context.bot

    async def create_and_check() -> None:
        try:
            try:
                with get_session() as session:
                    rec, updated = WatchRepository(session).create_or_update(
                        user_id, service_id, office_id, when
                    )
            except LimitReached:
                await _show_limit(bot, user_id, chat_id, message_id, lang)
                return
            with running_immediate_check(rec.id):
                await _check_and_show(
                    bot, user_id, chat_id, message_id, rec.id, updated, lang
                )
            await track_event(
                "watch_saved",
                user_id=user_id,
                service_id=service_id,
                when_kind=when.kind,
                updated=updated,
            )
        finally:
            _clear_checking(context, message_id)

    run_for_user(context, update, user_id, create_and_check())


async def start_recheck(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    watch_id: int,
    when: WhenSpec,
    *,
    target_message_id: int | None,
) -> None:
    """When WatchRepository.set_when returns another watch (an ended watch whose service
    already has an open one), the live alert of `watch_id` is closed as outdated under
    alert_lock(watch_id), or only cleared when it is the target message, and the result
    carries alert.updated_existing."""
    user_id = update.effective_user.id
    with get_session() as session:
        pressed = WatchRepository(session).get_for_user(watch_id, user_id)
    if pressed is None:
        return
    lang = get_user_language(user_id, context)
    message_id = await _show_checking(
        update, context, user_id, pressed.service_id, target_message_id, lang
    )
    if message_id is None:
        return
    context.user_data[CHECKING_KEY] = message_id
    chat_id = update.effective_chat.id
    bot = context.bot

    async def close_pressed_alert() -> None:
        async with alert_lock(watch_id):
            with get_session() as session:
                rec = WatchRepository(session).get(watch_id)
            if rec is None or rec.live is None:
                return
            if (rec.live.chat_id, rec.live.message_id) == (chat_id, message_id):
                with get_session() as session:
                    WatchRepository(session).clear_live_alert(
                        watch_id, reset_alerted=True
                    )
            else:
                await close_live_alert(
                    bot, watch_id, FinalState.OUTDATED, lang, by_user=True
                )

    async def change_and_check() -> None:
        try:
            try:
                with get_session() as session:
                    rec = WatchRepository(session).set_when(watch_id, when)
            except LimitReached:
                await _show_limit(bot, user_id, chat_id, message_id, lang)
                return
            updated = rec.id != watch_id
            with running_immediate_check(rec.id):
                if updated:
                    await close_pressed_alert()
                await _check_and_show(
                    bot, user_id, chat_id, message_id, rec.id, updated, lang
                )
        finally:
            _clear_checking(context, message_id)

    run_for_user(context, update, user_id, change_and_check())
