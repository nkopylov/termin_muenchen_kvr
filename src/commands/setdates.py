"""
/setdates command - Set date range for appointment search
"""

import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import UserRepository
from src.services.analytics_service import track_event

logger = logging.getLogger(__name__)


async def setdates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setdates command to set date range"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

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
                    t("setdates.btn_next_2_days", lang, start=today_str, end=date_2),
                    callback_data="setdates:2",
                )
            ],
            [
                InlineKeyboardButton(
                    t("setdates.btn_next_week", lang, start=today_str, end=date_7),
                    callback_data="setdates:7",
                )
            ],
            [
                InlineKeyboardButton(
                    t("setdates.btn_next_30_days", lang, start=today_str, end=date_30),
                    callback_data="setdates:30",
                )
            ],
            [
                InlineKeyboardButton(
                    t("setdates.btn_next_3_months", lang, start=today_str, end=date_90),
                    callback_data="setdates:90",
                )
            ],
            [
                InlineKeyboardButton(
                    t(
                        "setdates.btn_next_6_months",
                        lang,
                        start=today_str,
                        end=date_180,
                    ),
                    callback_data="setdates:180",
                )
            ],
            [
                InlineKeyboardButton(
                    t("common.btn_main_menu", lang), callback_data="main_menu"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            t("setdates.presets", lang),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            t("setdates.invalid_format", lang),
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
                t("setdates.invalid_range", lang),
                parse_mode="HTML",
            )
            return

    except ValueError:
        await update.message.reply_text(
            t("setdates.invalid_date", lang),
            parse_mode="HTML",
        )
        return

    with get_session() as session:
        user_repo = UserRepository(session)
        user_repo.set_date_range(user_id, start_date, end_date)

    # Track date range change
    range_days = (end_dt - start_dt).days
    await track_event(
        "date_range_set", user_id=user_id, range_days=range_days, range_direction="set"
    )

    await update.message.reply_text(
        t("setdates.updated", lang, start_date=start_date, end_date=end_date),
        parse_mode="HTML",
    )
    logger.info(f"User {user_id} set date range: {start_date} to {end_date}")
