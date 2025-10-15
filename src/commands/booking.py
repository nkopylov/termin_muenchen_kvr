"""
Booking conversation handler for Telegram bot
Manages the multi-step booking process with user interaction
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.booking_api import book_appointment_complete
from src.termin_tracker import get_available_slots
from src.database import get_session
from src.repositories import BookingSessionRepository
from src.services.analytics_service import track_event
from src.services.appointment_checker import (
    increment_bookings_started,
    increment_bookings_completed,
)
from src.services_manager import get_service_info

logger = logging.getLogger(__name__)

# Booking session timeout (15 minutes)
BOOKING_SESSION_TIMEOUT_SECONDS = 900

# Conversation states
(
    SELECTING_TIME,
    ASKING_NAME,
    ASKING_EMAIL,
    CONFIRMING,
) = range(4)


def create_booking_session(
    user_id: int,
    service_id: int,
    office_id: int,
    date: str,
    captcha_token: str,
    state: str = "SELECTING_TIME",
) -> None:
    """Create a new booking session in the database"""
    from datetime import timedelta

    expires_at = datetime.utcnow() + timedelta(seconds=BOOKING_SESSION_TIMEOUT_SECONDS)

    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        booking_repo.create_session(
            user_id=user_id,
            state=state,
            service_id=service_id,
            office_id=office_id,
            date=date,
            captcha_token=captcha_token,
            expires_at=expires_at,
        )
    logger.info(f"User {user_id} entered booking mode - notifications paused")


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


def get_booking_session(user_id: int):
    """Get booking session data"""
    with get_session() as session:
        booking_repo = BookingSessionRepository(session)
        booking_session = booking_repo.get_session(user_id)
        if booking_session:
            # Eagerly load all attributes while session is active
            _ = (
                booking_session.state,
                booking_session.service_id,
                booking_session.office_id,
                booking_session.date,
                booking_session.captcha_token,
                booking_session.timestamp,
                booking_session.name,
                booking_session.email,
                booking_session.created_at,
                booking_session.updated_at,
                booking_session.expires_at,
            )
            # Detach from session to prevent DetachedInstanceError
            session.expunge(booking_session)
        return booking_session


async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the booking process - show available dates
    Triggered by callback query from appointment notification
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # Extract data from callback (format: "book_DATE_OFFICEID_SERVICEID")
    callback_data = query.data.split("_")
    if len(callback_data) >= 4:
        date = callback_data[1]
        office_id = int(callback_data[2])
        service_id = int(callback_data[3])

        await query.edit_message_text(
            f"📅 Selected date: {date}\n\n" f"Fetching available time slots..."
        )

        # Fetch available time slots for this date
        captcha_token = context.bot_data.get("captcha_token")
        if not captcha_token:
            logger.warning(f"User {user_id} - captcha token expired")
            await query.edit_message_text(
                "❌ Error: Captcha token expired. Please try again from the appointment notification."
            )
            return ConversationHandler.END

        slots_data = get_available_slots(date, office_id, service_id, captcha_token)

        if not slots_data or not slots_data.get("offices"):
            logger.info(f"User {user_id} - no slots available for {date}")
            await query.edit_message_text(
                f"❌ No available time slots found for {date}.\n"
                f"They may have been booked already. Please try another date."
            )
            return ConversationHandler.END

        # Extract appointments (timestamps)
        appointments = []
        for office in slots_data.get("offices", []):
            if office.get("officeId") == int(office_id):
                appointments = office.get("appointments", [])
                break

        if not appointments:
            logger.info(f"User {user_id} - no appointments available for {date}")
            await query.edit_message_text(f"❌ No time slots available for {date}.")
            return ConversationHandler.END

        # Create booking session in DB
        create_booking_session(
            user_id=user_id,
            service_id=service_id,
            office_id=office_id,
            date=date,
            captcha_token=captcha_token,
            state="SELECTING_TIME",
        )

        # Increment booking started stats
        increment_bookings_started()

        # Track booking started
        service_info = get_service_info(service_id)
        await track_event(
            "booking_started",
            user_id=user_id,
            service_id=service_id,
            service_name=service_info["name"]
            if service_info
            else f"Service {service_id}",
            office_id=office_id,
            selected_date=date,
        )

        # Create inline keyboard with time slots
        keyboard = []
        for timestamp in appointments[:10]:  # Show first 10 slots
            dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Europe/Berlin"))
            time_str = dt.strftime("%H:%M")
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🕐 {time_str}", callback_data=f"time_{timestamp}"
                    )
                ]
            )

        keyboard.append(
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_booking")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📅 Available time slots for {date}:\n\n" f"Please select a time:",
            reply_markup=reply_markup,
        )

        return SELECTING_TIME

    else:
        logger.warning(f"User {user_id} - invalid booking data format")
        await query.edit_message_text("❌ Invalid booking data. Please try again.")
        return ConversationHandler.END


async def time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    User selected a time slot - ask for their name
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "cancel_booking":
        booking_session = get_booking_session(user_id)
        if booking_session:
            # Track booking cancelled
            await track_event(
                "booking_cancelled",
                user_id=user_id,
                service_id=booking_session.service_id,
                cancelled_at_step="time_selection",
                reason="user_initiated",
            )
        delete_booking_session(user_id)
        await query.edit_message_text("❌ Booking cancelled.")
        return ConversationHandler.END

    # Check if session still exists (bot might have restarted)
    booking_session = get_booking_session(user_id)
    if not booking_session:
        await query.edit_message_text(
            "❌ Your booking session expired or was cleared.\n\n"
            "Please start a new booking from an appointment notification."
        )
        return ConversationHandler.END

    # Extract timestamp
    timestamp = int(query.data.split("_")[1])

    # Update session with selected timestamp
    update_booking_session(user_id, timestamp=timestamp, state="ASKING_NAME")

    # Track slot selected
    dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Europe/Berlin"))
    await track_event(
        "slot_selected",
        user_id=user_id,
        service_id=booking_session.service_id,
        selected_time=dt.strftime("%H:%M"),
    )

    time_str = dt.strftime("%H:%M on %Y-%m-%d")

    keyboard = [
        [InlineKeyboardButton("❌ Cancel Booking", callback_data="cancel_booking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Selected time: {time_str}\n\n"
        f"Please enter your full name (as it appears on your documents):",
        reply_markup=reply_markup,
    )

    return ASKING_NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Received user's name - ask for email
    """
    user_id = update.effective_user.id
    name = update.message.text.strip()

    # Validate name has at least 2 words (first + last name)
    name_parts = name.split()
    if len(name_parts) < 2:
        await update.message.reply_text(
            "❌ Please enter your full name (first and last name).\n\n"
            "Example: John Smith"
        )
        return ASKING_NAME

    if len(name) < 4:
        await update.message.reply_text(
            "❌ Name is too short. Please enter your full name:"
        )
        return ASKING_NAME

    # Update session with name
    update_booking_session(user_id, name=name, state="ASKING_EMAIL")

    # Track name entered (without tracking the actual name for privacy)
    booking_session = get_booking_session(user_id)
    if booking_session:
        await track_event(
            "name_entered",
            user_id=user_id,
            service_id=booking_session.service_id,
            step_number=2,
        )

    keyboard = [
        [InlineKeyboardButton("❌ Cancel Booking", callback_data="cancel_booking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Name: {name}\n\n"
        f"Please enter your email address (you'll receive a confirmation email):",
        reply_markup=reply_markup,
    )

    return ASKING_EMAIL


async def email_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Received user's email - show confirmation and process booking
    """
    import re

    user_id = update.effective_user.id
    email = update.message.text.strip().lower()

    # Proper email validation using regex
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        await update.message.reply_text(
            "❌ Invalid email address. Please enter a valid email:\n\n"
            "Example: your.name@example.com"
        )
        return ASKING_EMAIL

    # Update session with email
    update_booking_session(user_id, email=email, state="CONFIRMING")

    # Get booking data from session
    booking_session = get_booking_session(user_id)
    if not booking_session:
        await update.message.reply_text("❌ Session expired. Please start again.")
        return ConversationHandler.END

    # Track email entered (without tracking the actual email for privacy)
    await track_event(
        "email_entered",
        user_id=user_id,
        service_id=booking_session.service_id,
        step_number=3,
    )

    dt = datetime.fromtimestamp(booking_session.timestamp, tz=ZoneInfo("Europe/Berlin"))
    time_str = dt.strftime("%H:%M on %A, %B %d, %Y")

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Booking", callback_data="confirm_booking")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_booking")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 <b>Please confirm your booking:</b>\n\n"
        f"🕐 Time: {time_str}\n"
        f"👤 Name: {booking_session.name}\n"
        f"📧 Email: {email}\n\n"
        f"<b>Important:</b> You will receive a confirmation email. "
        f"You MUST click the link in that email to finalize your appointment!",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )

    return CONFIRMING


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    User confirmed - process the booking
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "cancel_booking":
        booking_session = get_booking_session(user_id)
        if booking_session:
            # Track booking cancelled
            await track_event(
                "booking_cancelled",
                user_id=user_id,
                service_id=booking_session.service_id,
                cancelled_at_step="confirmation",
                reason="user_initiated",
            )
        delete_booking_session(user_id)
        await query.edit_message_text("❌ Booking cancelled.")
        return ConversationHandler.END

    # Get booking data from session
    booking_session = get_booking_session(user_id)
    if not booking_session:
        await query.edit_message_text("❌ Session expired. Please start again.")
        return ConversationHandler.END

    # Track booking confirmed
    await track_event(
        "booking_confirmed",
        user_id=user_id,
        service_id=booking_session.service_id,
        step_number=4,
    )

    timestamp = booking_session.timestamp
    office_id = booking_session.office_id
    service_id = booking_session.service_id
    name = booking_session.name
    email = booking_session.email
    captcha_token = booking_session.captcha_token
    booking_start_time = booking_session.created_at

    await query.edit_message_text(
        "⏳ Processing your booking...\n" "This may take a few seconds."
    )

    # Perform the booking
    try:
        result = book_appointment_complete(
            timestamp=timestamp,
            office_id=office_id,
            service_id=service_id,
            captcha_token=captcha_token,
            family_name=name,
            email=email,
        )

        # Calculate duration
        duration_ms = int(
            (datetime.utcnow() - booking_start_time).total_seconds() * 1000
        )

        if result:
            process_id = result.get("processId")
            dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("Europe/Berlin"))
            time_str = dt.strftime("%H:%M on %A, %B %d, %Y")

            # Increment booking completed stats
            increment_bookings_completed()

            # Track booking completed (success)
            service_info = get_service_info(service_id)
            await track_event(
                "booking_completed",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"]
                if service_info
                else f"Service {service_id}",
                status="success",
                duration_ms=duration_ms,
                booking_id=process_id,
            )

            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🎉 <b>Booking Successful!</b> 🎉\n\n"
                f"📋 Booking ID: {process_id}\n"
                f"🕐 Time: {time_str}\n"
                f"👤 Name: {name}\n"
                f"📧 Email: {email}\n\n"
                f"<b>⚠️ IMPORTANT - Next Steps:</b>\n\n"
                f"1. Check your email inbox at <b>{email}</b>\n"
                f"2. Look for a confirmation email from Munich Ausländerbehörde\n"
                f"3. <b>Click the confirmation link</b> in that email\n"
                f"4. Your appointment will only be finalized after email confirmation\n\n"
                f"If you don't see the email within 5 minutes, check your spam folder.",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            # Track booking completed (failure)
            service_info = get_service_info(service_id)
            await track_event(
                "booking_completed",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"]
                if service_info
                else f"Service {service_id}",
                status="failure",
                failure_reason="slot_taken_or_api_error",
                duration_ms=duration_ms,
            )

            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "❌ <b>Booking Failed</b>\n\n"
                "The appointment could not be booked. Possible reasons:\n"
                "• The slot was just taken by someone else\n"
                "• Network error occurred\n"
                "• Captcha token expired\n\n"
                "Please try booking another available slot.",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Booking error: {e}")
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"❌ An error occurred while booking:\n{str(e)}\n\n"
            f"Please try again or contact support.",
            reply_markup=reply_markup,
        )

    # Remove booking session - resumes notifications
    delete_booking_session(user_id)
    context.user_data.clear()

    return ConversationHandler.END


async def cancel_booking_button(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle cancel booking button press during interactive states"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    booking_session = get_booking_session(user_id)
    if booking_session:
        # Determine at which step the cancellation happened
        step_map = {
            "ASKING_NAME": "name_entry",
            "ASKING_EMAIL": "email_entry",
        }
        cancelled_at_step = step_map.get(booking_session.state, "unknown")

        # Track booking cancelled
        await track_event(
            "booking_cancelled",
            user_id=user_id,
            service_id=booking_session.service_id,
            cancelled_at_step=cancelled_at_step,
            reason="user_initiated",
        )

    delete_booking_session(user_id)

    await query.edit_message_text("❌ Booking cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_booking_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Cancel the booking conversation"""
    user_id = update.effective_user.id
    booking_session = get_booking_session(user_id)
    if booking_session:
        # Track booking cancelled
        await track_event(
            "booking_cancelled",
            user_id=user_id,
            service_id=booking_session.service_id,
            cancelled_at_step="unknown",
            reason="user_initiated",
        )

    delete_booking_session(user_id)

    await update.message.reply_text("❌ Booking cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# Create the conversation handler
booking_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_booking, pattern=r"^book_\d{4}-\d{2}-\d{2}_\d+_\d+$")
    ],
    states={
        SELECTING_TIME: [
            CallbackQueryHandler(time_selected, pattern=r"^(time_\d+|cancel_booking)$")
        ],
        ASKING_NAME: [
            CallbackQueryHandler(cancel_booking_button, pattern=r"^cancel_booking$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, name_received),
        ],
        ASKING_EMAIL: [
            CallbackQueryHandler(cancel_booking_button, pattern=r"^cancel_booking$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, email_received),
        ],
        CONFIRMING: [
            CallbackQueryHandler(
                confirm_booking, pattern=r"^(confirm_booking|cancel_booking)$"
            )
        ],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_booking_conversation)],
)
