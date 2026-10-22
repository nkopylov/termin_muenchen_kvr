"""
/myservices command - Show user's active subscriptions
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import SubscriptionRepository
from src.services_manager import get_office_name, get_service_info

logger = logging.getLogger(__name__)


async def myservices_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show user's active subscriptions"""
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)

    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        keyboard = [
            [
                InlineKeyboardButton(
                    t("menu.btn_subscribe", lang), callback_data="categories"
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
            t("myservices.empty", lang),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    message = t("myservices.header", lang)

    for sub in subscriptions:
        service_info = get_service_info(sub["service_id"])
        if service_info:
            office_id = sub.get("office_id")
            office_name = (
                get_office_name(office_id, lang)
                if office_id
                else t("myservices.unknown_office", lang)
            )
            message += t(
                "myservices.item",
                lang,
                service=service_info["name"],
                office=office_name,
                date=sub["subscribed_at"][:10],
            )

    message += t("myservices.total", lang, count=len(subscriptions))

    # Add unsubscribe buttons
    keyboard = []
    if len(subscriptions) <= 10:
        for sub in subscriptions:
            service_info = get_service_info(sub["service_id"])
            if service_info:
                name = service_info["name"]
                if len(name) > 30:
                    name = name[:27] + "..."
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🗑 {name}", callback_data=f"unsub:{sub['service_id']}"
                        )
                    ]
                )

    # Add navigation buttons
    keyboard.append(
        [
            InlineKeyboardButton(
                t("myservices.btn_subscribe_more", lang), callback_data="categories"
            )
        ]
    )
    if len(subscriptions) > 0:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("myservices.btn_unsubscribe_all", lang),
                    callback_data="unsub_all",
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                t("common.btn_main_menu", lang), callback_data="main_menu"
            )
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        message, reply_markup=reply_markup, parse_mode="HTML"
    )
