# ABOUTME: Booking conversation: Book on an alert, pick a time, give contact details, book with the city.
# ABOUTME: The DB booking session is the source of truth; slow city calls run as background tasks.
"""
Booking conversation handler for Telegram bot
Manages the multi-step booking process with user interaction
"""

import html
import logging
import re
import warnings
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from functools import wraps
from typing import NoReturn
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from src import booking_api
from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import (
    BookingSessionRecord,
    BookingSessionRepository,
    PendingRetireRepository,
    UserRepository,
    WatchRepository,
)
from src.services.analytics_service import track_event
from src.services.appointment_checker import (
    increment_bookings_completed,
    increment_bookings_started,
)
from src.services_manager import get_service_info
from src.ui import callbacks as cb
from src.ui.background import run_for_user
from src.ui.callbacks import BOOK_DAY_RE, NAV_RE
from src.ui.keyboard import MENU_FILTER
from src.ui.telegram_safe import (
    EditOutcome,
    safe_answer,
    safe_edit_text,
    safe_send,
    safe_strip_markup,
)
from src.watches import availability, when
from src.watches.alert_ops import alert_lock, close_live_alert
from src.watches.alert_view import FinalState
from src.watches.labels import SEPARATOR, day_label, office_label, service_label
from src.watches.slots import SlotTime

logger = logging.getLogger(__name__)

# Booking session timeout (15 minutes)
BOOKING_SESSION_TIMEOUT_SECONDS = 900
MAX_TIME_BUTTONS = 12
BERLIN = ZoneInfo("Europe/Berlin")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Book buttons of alerts sent before the "b1:" scheme: book_<date>_<office>_<service>
LEGACY_BOOK_RE = r"^book_\d{4}-\d{2}-\d{2}_\d+_\d+$"
BOOK_TIME_RE = r"^b1:t:\d{1,10}:\d{1,10}$"
BOOK_CONFIRM_RE = r"^b1:(ok|me)$"
BOOK_CHANGE_RE = r"^b1:chg$"
BOOK_CANCEL_RE = r"^b1:x$"
# Menu labels are navigation, not a name or an email
TEXT_INPUT = filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & ~MENU_FILTER

# Conversation states
(
    SELECTING_TIME,
    ASKING_NAME,
    ASKING_EMAIL,
    CONFIRMING,
) = range(4)
END = ConversationHandler.END

# Analytics names of the step a booking was cancelled at
CANCEL_STEPS = {
    "SELECTING_TIME": "time_selection",
    "ASKING_NAME": "name_entry",
    "ASKING_EMAIL": "email_entry",
    "CONFIRMING": "confirmation",
}


# Booking session (one per user, in the DB)


def create_booking_session(
    user_id: int,
    service_id: int,
    office_id: int,
    day: date,
    *,
    watch_id: int | None,
    message_id: int,
) -> BookingSessionRecord | None:
    """Start the user's booking session, replacing any other; returns the replaced one"""
    expires_at = when.utcnow() + timedelta(seconds=BOOKING_SESSION_TIMEOUT_SECONDS)
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        previous = booking_repo.get_active(user_id)
        booking_repo.create_session(
            user_id=user_id,
            state="SELECTING_TIME",
            service_id=service_id,
            office_id=office_id,
            date=day.isoformat(),
            captcha_token="",
            expires_at=expires_at,
            watch_id=watch_id,
            message_id=message_id,
        )
    logger.info(f"User {user_id} entered booking mode - notifications paused")
    return previous


def update_booking_session(user_id: int, **kwargs) -> None:
    """Update booking session with new data"""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        booking_repo.update_session(user_id, **kwargs)


def delete_booking_session(user_id: int) -> None:
    """Delete booking session - resumes notifications"""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        booking_repo.delete_session(user_id)
    logger.info(f"User {user_id} exited booking mode - notifications resumed")


def get_active_session(user_id: int) -> BookingSessionRecord | None:
    """The user's unexpired booking session"""
    with get_session() as session:
        return BookingSessionRepository(session).get_active(user_id)


def _end_session_of(user_id: int, message_id: int) -> None:
    """Delete the user's session if it still belongs to the booking message `message_id`
    (the user may have started another booking meanwhile)"""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        row = booking_repo.get_session(user_id)
        if row is not None and row.message_id == message_id:
            booking_repo.delete_session(user_id)
            logger.info(f"User {user_id} exited booking mode - notifications resumed")


def _still_watching(user_id: int, watch_id: int | None) -> bool:
    """Whether the checker keeps looking for the booking's watch, so new days will follow"""
    if watch_id is None:
        return False
    with get_session() as session:
        rec = WatchRepository(session).get_for_user(watch_id, user_id)
    return rec is not None and rec.status == "active"


def _saved_contact(user_id: int) -> tuple[str, str] | None:
    with get_session() as session:
        return UserRepository(session).get_booking_contact(user_id)


# Validation and formatting


def name_error(name: str) -> str | None:
    """Catalog key describing what is wrong with a typed full name, or None if it is fine"""
    # At least 2 words (first + last name)
    if len(name.split()) < 2:
        return "booking.name_not_full"
    if len(name) < 4:
        return "booking.name_too_short"
    return None


def is_valid_email(email: str) -> bool:
    return EMAIL_RE.match(email) is not None


def _berlin(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=BERLIN)


def format_time_on_date(dt: datetime, lang: str) -> str:
    """Slot time with its day, e.g. "Wed 15.01, 10:30"."""
    return t(
        "booking.time_on_date",
        lang,
        time=dt.strftime("%H:%M"),
        date=day_label(dt.date(), lang),
    )


def format_time_on_long_date(dt: datetime, lang: str) -> str:
    """Slot time with weekday and month names, e.g. "10:30 on Wednesday, January 15, 2025"."""
    return t(
        "booking.time_on_long_date",
        lang,
        time=dt.strftime("%H:%M"),
        weekday=t(f"booking.weekday_{dt.weekday()}", lang),
        month=t(f"booking.month_{dt.month}", lang),
        day=dt.day,
        year=dt.year,
    )


def time_button_label(
    slot: SlotTime, service_id: int, show_office: bool, lang: str
) -> str:
    clock = _berlin(slot.ts).strftime("%H:%M")
    if not show_office:
        return clock
    return f"{clock}{SEPARATOR}{office_label(slot.office_id, service_id, lang)}"


def times_markup(
    times: tuple[SlotTime, ...], service_id: int, show_office: bool, lang: str
) -> InlineKeyboardMarkup:
    """Time buttons, two per row (one per row with office names), then Cancel"""
    buttons = [
        InlineKeyboardButton(
            time_button_label(slot, service_id, show_office, lang),
            callback_data=cb.book_time(slot.office_id, slot.ts),
        )
        for slot in times[:MAX_TIME_BUTTONS]
    ]
    per_row = 1 if show_office else 2
    rows = [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]
    rows.append(
        [
            InlineKeyboardButton(
                t("booking.btn_cancel", lang), callback_data=cb.book_cancel()
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _cancel_markup(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("booking.btn_cancel", lang),
                    callback_data=cb.book_cancel(),
                )
            ]
        ]
    )


def _service_name(service_id: int) -> str:
    """The service's German catalog name, as the city expects it"""
    info = get_service_info(service_id)
    return info["name"] if info else f"Service {service_id}"


# Entry: Book tapped on an alert


async def book_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NoReturn:
    """Book tapped on a watch's alert (b1:<watch>:<day>): the message leaves the watch's
    alert lifecycle and becomes the booking message; times are fetched in the background"""
    # Toasts keep the conversation state (None): a booking may be running on another message
    query = update.callback_query
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    parsed = cb.parse(query.data)
    if parsed is None:
        await safe_answer(query, t("booking.invalid_data", lang))
        raise ApplicationHandlerStop(None)
    watch_id, day = parsed.args
    with get_session() as session:
        rec = WatchRepository(session).get_for_user(watch_id, user_id)
    if rec is None or not rec.is_open:
        await safe_answer(query, t("booking.watch_ended", lang))
        raise ApplicationHandlerStop(None)

    await _start_booking(
        update,
        context,
        lang,
        service_id=rec.service_id,
        office_ids=availability.watch_office_ids(rec),
        session_office_id=rec.office_id or 0,
        day=day,
        watch_id=watch_id,
    )


async def book_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NoReturn:
    """Book tapped on an alert sent before watches (book_<date>_<office>_<service>)"""
    query = update.callback_query
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    _, day_raw, office_raw, service_raw = query.data.split("_")
    try:
        day = date.fromisoformat(day_raw)
    except ValueError:
        logger.warning(f"User {user_id} - invalid booking data format")
        await safe_answer(query, t("booking.invalid_data", lang))
        raise ApplicationHandlerStop(None) from None

    service_id, office_id = int(service_raw), int(office_raw)
    await _start_booking(
        update,
        context,
        lang,
        service_id=service_id,
        office_ids=[office_id],
        session_office_id=office_id,
        day=day,
        watch_id=_legacy_watch_id(user_id, service_id, office_id),
    )


def _legacy_watch_id(user_id: int, service_id: int, office_id: int) -> int | None:
    """The open watch that took over the subscription the old alert was sent for"""
    with get_session() as session:
        rec = WatchRepository(session).find_open(user_id, service_id)
    if rec is None:
        return None
    if rec.office_id is None or office_id in availability.watch_office_ids(rec):
        return rec.id
    return None


def _detach(watch_id: int, chat_id: int, message_id: int) -> None:
    """The tapped message now belongs to the booking: neither the checker nor the retire
    queue may edit it any more. The caller holds alert_lock(watch_id)."""
    with get_session() as session:
        watches = WatchRepository(session)
        rec = watches.get(watch_id)
        live = rec.live if rec is not None else None
        if live is not None and (live.chat_id, live.message_id) == (
            chat_id,
            message_id,
        ):
            watches.clear_live_alert(watch_id, reset_alerted=True)
        else:
            PendingRetireRepository(session).discard(chat_id, message_id)


async def _start_booking(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    lang: str,
    *,
    service_id: int,
    office_ids: list[int],
    session_office_id: int,
    day: date,
    watch_id: int | None,
) -> NoReturn:
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id, message_id = query.message.chat_id, query.message.message_id
    await safe_answer(query)

    existing = get_active_session(user_id)
    if existing is not None and existing.message_id == message_id:
        # A second tap on the same Book button; its booking is already starting
        raise ApplicationHandlerStop(None)

    def open_session() -> BookingSessionRecord | None:
        return create_booking_session(
            user_id,
            service_id,
            session_office_id,
            day,
            watch_id=watch_id,
            message_id=message_id,
        )

    if watch_id is None:
        with get_session() as session:
            PendingRetireRepository(session).discard(chat_id, message_id)
        previous = open_session()
    else:
        async with alert_lock(watch_id):
            _detach(watch_id, chat_id, message_id)
            previous = open_session()

    await safe_edit_text(
        context.bot,
        chat_id,
        message_id,
        t("booking.fetching_slots", lang, date=day_label(day, lang)),
    )
    if previous is not None and previous.message_id not in (None, message_id):
        await safe_strip_markup(context.bot, chat_id, previous.message_id)

    run_for_user(
        context,
        update,
        user_id,
        _show_times(
            context.bot,
            user_id,
            chat_id,
            message_id,
            service_id,
            office_ids,
            day,
            lang,
            watch_id,
        ),
    )
    raise ApplicationHandlerStop(SELECTING_TIME)


async def _show_times(
    bot,
    user_id: int,
    chat_id: int,
    message_id: int,
    service_id: int,
    office_ids: list[int],
    day: date,
    lang: str,
    watch_id: int | None,
) -> None:
    """Background part of a Book tap: fetch the day's times (fresh captcha token inside)"""
    if day < when.today_berlin():
        times: tuple[SlotTime, ...] | None = ()
    else:
        times = await availability.fetch_day_times(service_id, office_ids, day)

    session = get_active_session(user_id)
    if session is None or session.message_id != message_id:
        return  # cancelled or replaced while the times were loading

    label = day_label(day, lang)
    if not times:
        key = "booking.times_failed" if times is None else "booking.day_gone"
        logger.info(f"User {user_id} - no times for {day} ({key})")
        text = t(key, lang, date=label)
        if _still_watching(user_id, watch_id):
            text += "\n\n" + t("booking.will_send_days", lang)
        await safe_edit_text(bot, chat_id, message_id, text)
        _end_session_of(user_id, message_id)
        return

    increment_bookings_started()
    await track_event(
        "booking_started",
        user_id=user_id,
        service_id=service_id,
        service_name=_service_name(service_id),
        office_id=session.office_id,
        selected_date=day.isoformat(),
    )
    outcome = await safe_edit_text(
        bot,
        chat_id,
        message_id,
        t("booking.select_time", lang, date=label),
        times_markup(times, service_id, _several_places(service_id, office_ids), lang),
    )
    if outcome in (EditOutcome.GONE, EditOutcome.FORBIDDEN):
        _end_session_of(user_id, message_id)


def _several_places(service_id: int, office_ids: list[int]) -> bool:
    """Whether the times can be at different places (offices sharing a queue are one)"""
    return len({office_label(o, service_id) for o in office_ids}) > 1


# Conversation steps

Step = Callable[
    [Update, ContextTypes.DEFAULT_TYPE, BookingSessionRecord], Awaitable[int]
]


def booking_step(handler: Step) -> Callable[..., Awaitable[int]]:
    """Runs a step only while the user's DB booking session is alive, then keeps group 1
    from also handling the update. Without a session the conversation ends silently and
    group 1 handles the update: typed text becomes a search, a button gets "session cleared"."""

    @wraps(handler)
    async def step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        session = get_active_session(update.effective_user.id)
        if session is None:
            return END
        query = update.callback_query
        if query is not None and session.message_id not in (
            None,
            query.message.message_id,
        ):
            await safe_answer(query)
            await safe_strip_markup(
                context.bot, query.message.chat_id, query.message.message_id
            )
            raise ApplicationHandlerStop(None)
        raise ApplicationHandlerStop(await handler(update, context, session))

    return step


async def _ask_name(
    bot, chat_id: int, message_id: int, timestamp: int, lang: str
) -> None:
    await safe_edit_text(
        bot,
        chat_id,
        message_id,
        t("booking.ask_name", lang, time=format_time_on_date(_berlin(timestamp), lang)),
        _cancel_markup(lang),
    )


async def _send_step(
    bot,
    session: BookingSessionRecord,
    chat_id: int,
    text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    """Send the next booking message with buttons; the previous one loses its buttons"""
    message, _ = await safe_send(bot, chat_id, text, markup)
    if session.message_id is not None:
        await safe_strip_markup(bot, chat_id, session.message_id)
    if message is not None:
        update_booking_session(session.user_id, message_id=message.message_id)


@booking_step
async def time_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Time picked: offer the saved contact details, or ask for the name"""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    office_id, timestamp = cb.parse(query.data).args
    chat_id, message_id = query.message.chat_id, query.message.message_id

    dt = _berlin(timestamp)
    await track_event(
        "slot_selected",
        user_id=user_id,
        service_id=session.service_id,
        selected_time=dt.strftime("%H:%M"),
    )

    contact = _saved_contact(user_id)
    if contact is None:
        update_booking_session(
            user_id, timestamp=timestamp, office_id=office_id, state="ASKING_NAME"
        )
        await _ask_name(context.bot, chat_id, message_id, timestamp, lang)
        return ASKING_NAME

    update_booking_session(
        user_id, timestamp=timestamp, office_id=office_id, state="CONFIRMING"
    )
    name, email = contact
    text = t(
        "booking.use_saved",
        lang,
        time=format_time_on_long_date(dt, lang),
        office=html.escape(office_label(office_id, session.service_id, lang)),
        name=html.escape(name),
        email=html.escape(email),
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("booking.btn_yes_book", lang), callback_data=cb.book_me()
                )
            ],
            [
                InlineKeyboardButton(
                    t("booking.btn_change", lang), callback_data=cb.book_change()
                )
            ],
            [
                InlineKeyboardButton(
                    t("booking.btn_cancel", lang), callback_data=cb.book_cancel()
                )
            ],
        ]
    )
    await safe_edit_text(context.bot, chat_id, message_id, text, markup)
    return CONFIRMING


@booking_step
async def change_contact(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Other contact details than the saved ones: ask for the name"""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    update_booking_session(user_id, state="ASKING_NAME")
    await _ask_name(
        context.bot,
        query.message.chat_id,
        query.message.message_id,
        session.timestamp,
        lang,
    )
    return ASKING_NAME


@booking_step
async def name_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Received user's name - ask for email"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    chat_id = update.effective_chat.id
    name = update.message.text.strip()

    error = name_error(name)
    if error is not None:
        await safe_send(context.bot, chat_id, t(error, lang))
        return ASKING_NAME

    update_booking_session(user_id, name=name, state="ASKING_EMAIL")

    # Track name entered (without tracking the actual name for privacy)
    await track_event(
        "name_entered",
        user_id=user_id,
        service_id=session.service_id,
        step_number=2,
    )

    await _send_step(
        context.bot,
        session,
        chat_id,
        t("booking.ask_email", lang, name=html.escape(name)),
        _cancel_markup(lang),
    )
    return ASKING_EMAIL


@booking_step
async def email_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Received user's email - show confirmation"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    chat_id = update.effective_chat.id
    email = update.message.text.strip().lower()

    if not is_valid_email(email):
        await safe_send(context.bot, chat_id, t("booking.email_invalid", lang))
        return ASKING_EMAIL

    update_booking_session(user_id, email=email, state="CONFIRMING")

    # Track email entered (without tracking the actual email for privacy)
    await track_event(
        "email_entered",
        user_id=user_id,
        service_id=session.service_id,
        step_number=3,
    )

    text = t(
        "booking.confirm_summary",
        lang,
        time=format_time_on_long_date(_berlin(session.timestamp), lang),
        name=html.escape(session.name or ""),
        email=html.escape(email),
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("booking.btn_confirm", lang), callback_data=cb.book_ok()
                )
            ],
            [
                InlineKeyboardButton(
                    t("booking.btn_cancel", lang), callback_data=cb.book_cancel()
                )
            ],
        ]
    )
    await _send_step(context.bot, session, chat_id, text, markup)
    return CONFIRMING


@booking_step
async def confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Confirmed (typed or saved contact details): book in the background"""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    chat_id, message_id = query.message.chat_id, query.message.message_id

    if query.data == cb.book_me():
        contact = _saved_contact(user_id)
        if contact is None:  # forgotten in Settings meanwhile
            update_booking_session(user_id, state="ASKING_NAME")
            await _ask_name(context.bot, chat_id, message_id, session.timestamp, lang)
            return ASKING_NAME
        name, email = contact
    else:
        name, email = session.name, session.email

    # Track booking confirmed
    await track_event(
        "booking_confirmed",
        user_id=user_id,
        service_id=session.service_id,
        step_number=4,
    )
    await safe_edit_text(
        context.bot, chat_id, message_id, t("booking.processing", lang)
    )
    run_for_user(
        context,
        update,
        user_id,
        _book(context.bot, session, name, email, chat_id, message_id, lang),
    )
    return END


@booking_step
async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: BookingSessionRecord
) -> int:
    """Cancel button of any booking message"""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    # Track booking cancelled
    await track_event(
        "booking_cancelled",
        user_id=user_id,
        service_id=session.service_id,
        cancelled_at_step=CANCEL_STEPS.get(session.state, "unknown"),
        reason="user_initiated",
    )
    delete_booking_session(user_id)
    await safe_edit_text(
        context.bot,
        query.message.chat_id,
        query.message.message_id,
        t("booking.cancelled", lang),
    )
    return END


async def leave_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A command, menu tap or navigation button during a booking ends the booking;
    group 1 then handles the same update"""
    user_id = update.effective_user.id
    session = get_active_session(user_id)
    if session is not None:
        await track_event(
            "booking_cancelled",
            user_id=user_id,
            service_id=session.service_id,
            cancelled_at_step=CANCEL_STEPS.get(session.state, "unknown"),
            reason="navigated_away",
        )
        delete_booking_session(user_id)
        if session.message_id is not None:
            # Its question must not stay: a typed answer would now become a search
            await safe_edit_text(
                context.bot,
                update.effective_chat.id,
                session.message_id,
                t("booking.cancelled", get_user_language(user_id, context)),
            )
    return END


# Booking with the city (background)


async def _end_watch_booked(bot, watch_id: int, user_id: int, lang: str) -> bool:
    """End the watch the booking came from; False if it was no longer open"""
    async with alert_lock(watch_id):
        with get_session() as session:
            watches = WatchRepository(session)
            rec = watches.get_for_user(watch_id, user_id)
            if rec is None or not rec.is_open:
                return False
            watches.set_status(watch_id, "ended", end_reason="booked")
        await close_live_alert(bot, watch_id, FinalState.BOOKED, lang, by_user=True)
    return True


async def _book(
    bot,
    session: BookingSessionRecord,
    name: str,
    email: str,
    chat_id: int,
    message_id: int,
    lang: str,
) -> None:
    """Background part of a confirmation: book, then show the outcome"""
    service_id = session.service_id
    booking_start_time = session.expires_at - timedelta(
        seconds=BOOKING_SESSION_TIMEOUT_SECONDS
    )

    result = None
    try:
        result = await booking_api.book_appointment(
            timestamp=session.timestamp,
            office_id=session.office_id,
            service_id=service_id,
            service_name=_service_name(service_id),
            family_name=name,
            email=email,
        )
    except Exception as e:  # noqa: BLE001 - the user must always get a final message
        logger.error(f"Booking error: {e}")
        text = t("booking.error", lang)
    else:
        duration_ms = int((when.utcnow() - booking_start_time).total_seconds() * 1000)
        if result:
            outcome = {"status": "success", "booking_id": result.get("processId")}
        else:
            outcome = {
                "status": "failure",
                "failure_reason": "slot_taken_or_api_error",
            }
        await track_event(
            "booking_completed",
            user_id=session.user_id,
            service_id=service_id,
            service_name=_service_name(service_id),
            duration_ms=duration_ms,
            **outcome,
        )
        if result:
            text = await _booked(bot, session, result, name, email, lang)
        else:
            text = t("booking.failed", lang)

    if not result and _still_watching(session.user_id, session.watch_id):
        text += "\n\n" + t("booking.will_update", lang)

    await safe_edit_text(bot, chat_id, message_id, text)
    # Removing the session resumes alerts; after the final text, so none arrives before it
    _end_session_of(session.user_id, message_id)


async def _booked(
    bot,
    session: BookingSessionRecord,
    result: dict,
    name: str,
    email: str,
    lang: str,
) -> str:
    """Remember the contact details, end the watch; returns the success text"""
    user_id = session.user_id
    with get_session() as db_session:
        UserRepository(db_session).set_booking_contact(user_id, name, email)
    increment_bookings_completed()

    text = t(
        "booking.success",
        lang,
        process_id=html.escape(str(result.get("processId"))),
        time=format_time_on_long_date(_berlin(session.timestamp), lang),
        name=html.escape(name),
        email=html.escape(email),
    )
    if session.watch_id is not None and await _end_watch_booked(
        bot, session.watch_id, user_id, lang
    ):
        text += "\n\n" + t(
            "booking.watch_finished",
            lang,
            service=html.escape(service_label(session.service_id, lang)),
        )
    return text


# Outside the conversation


async def booking_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Booking buttons pressed outside a running booking conversation (restart, expiry)"""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    chat_id, message_id = query.message.chat_id, query.message.message_id

    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        active = booking_repo.get_active(user_id)
        if active is not None and active.message_id == message_id:
            # A repeated tap on the running booking's message (a step already moved on,
            # or the booking with the city is in progress)
            return
        row = booking_repo.get_session(user_id)
        # A booking running on another message stays
        if row is not None and row.message_id in (None, message_id):
            booking_repo.delete_session(user_id)

    await safe_edit_text(
        context.bot, chat_id, message_id, t("booking.session_cleared", lang)
    )


async def end_all_booking_sessions(bot) -> int:
    """End every booking session left from before a restart; returns how many"""
    with get_session() as session:
        ended = BookingSessionRepository(session).pop_all_sessions()
    for record in ended:
        if record.message_id is not None:
            lang = get_user_language(record.user_id)
            await safe_edit_text(
                bot,
                record.user_id,
                record.message_id,
                t("booking.session_cleared", lang),
            )
    if ended:
        logger.info(f"Ended {len(ended)} booking sessions left from before the restart")
    return len(ended)


def build_booking_conversation() -> ConversationHandler:
    with warnings.catch_warnings():
        # Tracked per user on purpose: one booking spans several of the user's messages
        warnings.filterwarnings(
            "ignore", message="If 'per_message=False'", category=PTBUserWarning
        )
        cancel_button = CallbackQueryHandler(cancel, pattern=BOOK_CANCEL_RE)
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(book_day, pattern=BOOK_DAY_RE),
                CallbackQueryHandler(book_legacy, pattern=LEGACY_BOOK_RE),
            ],
            states={
                SELECTING_TIME: [
                    CallbackQueryHandler(time_selected, pattern=BOOK_TIME_RE),
                    cancel_button,
                ],
                ASKING_NAME: [MessageHandler(TEXT_INPUT, name_received), cancel_button],
                ASKING_EMAIL: [
                    MessageHandler(TEXT_INPUT, email_received),
                    cancel_button,
                ],
                CONFIRMING: [
                    CallbackQueryHandler(confirm, pattern=BOOK_CONFIRM_RE),
                    CallbackQueryHandler(change_contact, pattern=BOOK_CHANGE_RE),
                    cancel_button,
                ],
            },
            fallbacks=[
                MessageHandler(filters.COMMAND | MENU_FILTER, leave_booking),
                CallbackQueryHandler(leave_booking, pattern=NAV_RE),
            ],
            allow_reentry=True,
        )


booking_conversation = build_booking_conversation()
