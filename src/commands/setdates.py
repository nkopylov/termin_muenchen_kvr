"""
/setdates command - Set date range for appointment search
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository

logger = logging.getLogger(__name__)


async def setdates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdates command to set date range"""
    user_id = update.effective_user.id

    if len(context.args) != 2:
        await update.message.reply_text(
            "📅 <b>Set Date Range</b>\n\n"
            "Usage: <code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
            "Example:\n"
            "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
            "This sets the date range for appointment searches.",
            parse_mode="HTML",
        )
        return

    start_date = context.args[0]
    end_date = context.args[1]

    # Basic validation
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
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
