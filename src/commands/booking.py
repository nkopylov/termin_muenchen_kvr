"""
Booking conversation handler for Telegram bot
Manages the multi-step booking process with user interaction
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from src.booking_api import book_appointment_complete
from src.termin_tracker import get_available_slots

logger = logging.getLogger(__name__)

# Conversation states
(
    SELECTING_DATE,
    SELECTING_TIME,
    ASKING_NAME,
    ASKING_EMAIL,
    CONFIRMING,
) = range(5)


async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the booking process - show available dates
    Triggered by callback query from appointment notification
    """
    query = update.callback_query
    await query.answer()

    # Mark user as in booking mode
    user_id = update.effective_user.id
    from src.services.queue_manager import add_user_to_queue
    add_user_to_queue(user_id)

    # Extract data from callback (format: "book_DATE_OFFICEID_SERVICEID")
    callback_data = query.data.split('_')
    if len(callback_data) >= 4:
        date = callback_data[1]
        office_id = callback_data[2]
        service_id = callback_data[3]

        # Store in context
        context.user_data['booking_date'] = date
        context.user_data['booking_office_id'] = office_id
        context.user_data['booking_service_id'] = service_id

        await query.edit_message_text(
            f"📅 Selected date: {date}\n\n"
            f"Fetching available time slots..."
        )

        # Fetch available time slots for this date
        captcha_token = context.bot_data.get('captcha_token')
        if not captcha_token:
            # Remove user from active booking mode
            from src.services.queue_manager import remove_user_from_queue
            remove_user_from_queue(user_id)
            logger.info(f"User {user_id} exited booking mode (token expired) - notifications resumed")
            await query.edit_message_text(
                "❌ Error: Captcha token expired. Please try again from the appointment notification."
            )
            return ConversationHandler.END

        slots_data = get_available_slots(date, office_id, service_id, captcha_token)

        if not slots_data or not slots_data.get('offices'):
            # Remove user from active booking mode
            from src.services.queue_manager import remove_user_from_queue
            remove_user_from_queue(user_id)
            logger.info(f"User {user_id} exited booking mode (no slots) - notifications resumed")
            await query.edit_message_text(
                f"❌ No available time slots found for {date}.\n"
                f"They may have been booked already. Please try another date."
            )
            return ConversationHandler.END

        # Extract appointments (timestamps)
        appointments = []
        for office in slots_data.get('offices', []):
            if office.get('officeId') == int(office_id):
                appointments = office.get('appointments', [])
                break

        if not appointments:
            # Remove user from active booking mode
            from src.services.queue_manager import remove_user_from_queue
            remove_user_from_queue(user_id)
            logger.info(f"User {user_id} exited booking mode (no appointments) - notifications resumed")
            await query.edit_message_text(
                f"❌ No time slots available for {date}."
            )
            return ConversationHandler.END

        # Create inline keyboard with time slots
        keyboard = []
        for timestamp in appointments[:10]:  # Show first 10 slots
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%H:%M")
            keyboard.append([
                InlineKeyboardButton(
                    f"🕐 {time_str}",
                    callback_data=f"time_{timestamp}"
                )
            ])

        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_booking")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"📅 Available time slots for {date}:\n\n"
            f"Please select a time:",
            reply_markup=reply_markup
        )

        return SELECTING_TIME

    else:
        # Remove user from active booking mode
        from telegram_bot import active_booking_users
        if user_id in active_booking_users:
            del active_booking_users[user_id]
            logger.info(f"User {user_id} exited booking mode (invalid data) - notifications resumed")
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
        # Remove user from active booking mode
        from telegram_bot import active_booking_users
        if user_id in active_booking_users:
            del active_booking_users[user_id]
            logger.info(f"User {user_id} exited booking mode (cancelled at time selection) - notifications resumed")
        await query.edit_message_text("❌ Booking cancelled.")
        return ConversationHandler.END

    # Extract timestamp
    timestamp = int(query.data.split('_')[1])
    context.user_data['booking_timestamp'] = timestamp

    dt = datetime.fromtimestamp(timestamp)
    time_str = dt.strftime("%H:%M on %Y-%m-%d")

    await query.edit_message_text(
        f"✅ Selected time: {time_str}\n\n"
        f"Please enter your full name (as it appears on your documents):"
    )

    return ASKING_NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Received user's name - ask for email
    """
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(
            "❌ Name is too short. Please enter your full name:"
        )
        return ASKING_NAME

    context.user_data['booking_name'] = name

    await update.message.reply_text(
        f"✅ Name: {name}\n\n"
        f"Please enter your email address (you'll receive a confirmation email):"
    )

    return ASKING_EMAIL


async def email_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Received user's email - show confirmation and process booking
    """
    email = update.message.text.strip()

    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ Invalid email address. Please enter a valid email:"
        )
        return ASKING_EMAIL

    context.user_data['booking_email'] = email

    # Show confirmation
    timestamp = context.user_data['booking_timestamp']
    name = context.user_data['booking_name']
    dt = datetime.fromtimestamp(timestamp)
    time_str = dt.strftime("%H:%M on %A, %B %d, %Y")

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Booking", callback_data="confirm_booking")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_booking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 <b>Please confirm your booking:</b>\n\n"
        f"🕐 Time: {time_str}\n"
        f"👤 Name: {name}\n"
        f"📧 Email: {email}\n\n"
        f"<b>Important:</b> You will receive a confirmation email. "
        f"You MUST click the link in that email to finalize your appointment!",
        parse_mode='HTML',
        reply_markup=reply_markup
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
        # Remove user from active booking mode
        from telegram_bot import active_booking_users
        if user_id in active_booking_users:
            del active_booking_users[user_id]
            logger.info(f"User {user_id} exited booking mode (cancelled) - notifications resumed")
        await query.edit_message_text("❌ Booking cancelled.")
        return ConversationHandler.END

    # Extract booking data
    timestamp = context.user_data['booking_timestamp']
    office_id = int(context.user_data['booking_office_id'])
    service_id = int(context.user_data['booking_service_id'])
    name = context.user_data['booking_name']
    email = context.user_data['booking_email']

    await query.edit_message_text(
        f"⏳ Processing your booking...\n"
        f"This may take a few seconds."
    )

    # Get fresh captcha token
    captcha_token = context.bot_data.get('captcha_token')
    if not captcha_token:
        await query.edit_message_text(
            "❌ Error: Captcha token expired. Please start over from the appointment notification."
        )
        return ConversationHandler.END

    # Perform the booking
    try:
        result = book_appointment_complete(
            timestamp=timestamp,
            office_id=office_id,
            service_id=service_id,
            captcha_token=captcha_token,
            family_name=name,
            email=email
        )

        if result:
            process_id = result.get('processId')
            dt = datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%H:%M on %A, %B %d, %Y")

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
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                f"❌ <b>Booking Failed</b>\n\n"
                f"The appointment could not be booked. Possible reasons:\n"
                f"• The slot was just taken by someone else\n"
                f"• Network error occurred\n"
                f"• Captcha token expired\n\n"
                f"Please try booking another available slot.",
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Booking error: {e}")
        await query.edit_message_text(
            f"❌ An error occurred while booking:\n{str(e)}\n\n"
            f"Please try again or contact support."
        )

    # Remove user from active booking mode
    from src.services.queue_manager import remove_user_from_queue
    remove_user_from_queue(user_id)
    logger.info(f"User {user_id} exited booking mode - notifications resumed")

    # Clear user data
    context.user_data.clear()

    return ConversationHandler.END


async def cancel_booking_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the booking conversation"""
    user_id = update.effective_user.id

    # Remove user from active booking mode
    from src.services.queue_manager import remove_user_from_queue
    remove_user_from_queue(user_id)
    logger.info(f"User {user_id} exited booking mode (command cancel) - notifications resumed")

    await update.message.reply_text("❌ Booking cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# Create the conversation handler
booking_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_booking, pattern=r'^book_\d{4}-\d{2}-\d{2}_\d+_\d+$')
    ],
    states={
        SELECTING_TIME: [
            CallbackQueryHandler(time_selected, pattern=r'^(time_\d+|cancel_booking)$')
        ],
        ASKING_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)
        ],
        ASKING_EMAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, email_received)
        ],
        CONFIRMING: [
            CallbackQueryHandler(confirm_booking, pattern=r'^(confirm_booking|cancel_booking)$')
        ],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_booking_conversation)
    ],
)
