"""
/setdates command - Set date range for appointment search
"""

import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository

logger = logging.getLogger(__name__)


async def setdates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdates command to set date range"""
    user_id = update.effective_user.id

    # If no arguments, show quick presets
    if len(context.args) == 0:
        today = datetime.now()

        # Calculate preset dates
        date_2 = (today + timedelta(days=2)).strftime("%Y-%m-%d")
        date_7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        date_30 = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        date_90 = (today + timedelta(days=90)).strftime("%Y-%m-%d")
        date_180 = (today + timedelta(days=180)).strftime("%Y-%m-%d")

        today_str = today.strftime("%Y-%m-%d")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton(
                    f"📅 Next 2 days ({today_str} to {date_2})",
                    callback_data="setdates:2",
                )
            ],
            [
                InlineKeyboardButton(
                    f"📅 Next week ({today_str} to {date_7})",
                    callback_data="setdates:7",
                )
            ],
            [
                InlineKeyboardButton(
                    f"📅 Next 30 days ({today_str} to {date_30})",
                    callback_data="setdates:30",
                )
            ],
            [
                InlineKeyboardButton(
                    f"📅 Next 3 months ({today_str} to {date_90})",
                    callback_data="setdates:90",
                )
            ],
            [
                InlineKeyboardButton(
                    f"📅 Next 6 months ({today_str} to {date_180})",
                    callback_data="setdates:180",
                )
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📅 <b>Set Date Range</b>\n\n"
            "Choose a preset date range or use a custom range:\n\n"
            "<b>Custom Range:</b>\n"
            "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
            "Example: <code>/setdates 2025-10-01 2025-10-31</code>",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Usage: <code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
            "Example:\n"
            "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
            "Or use /setdates without arguments for quick presets.",
            parse_mode="HTML",
        )
        return

    start_date = context.args[0]
    end_date = context.args[1]

    # Basic validation
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Validate end_date > start_date
        if end_dt <= start_dt:
            await update.message.reply_text(
                "❌ Invalid date range. End date must be after start date.\n\n"
                "Example: <code>/setdates 2025-10-01 2025-10-31</code>",
                parse_mode="HTML",
            )
            return

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format. Please use YYYY-MM-DD\n\n"
            "Example: <code>/setdates 2025-10-01 2025-10-31</code>",
            parse_mode="HTML",
        )
        return

    with get_session() as session:
        user_repo = UserRepository(session)
        user_repo.set_date_range(user_id, start_date, end_date)

    await update.message.reply_text(
        f"✅ Date range updated!\n\n"
        f"From: <b>{start_date}</b>\n"
        f"To: <b>{end_date}</b>\n\n"
        f"The bot will now search for appointments in this date range.",
        parse_mode="HTML",
    )
    logger.info(f"User {user_id} set date range: {start_date} to {end_date}")
