"""
/myservices command - Show user's active subscriptions
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import SubscriptionRepository
from src.services_manager import get_service_info

logger = logging.getLogger(__name__)


async def myservices_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show user's active subscriptions"""
    user_id = update.effective_user.id

    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        keyboard = [
            [InlineKeyboardButton("📋 Subscribe to Services", callback_data="main_menu")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📋 <b>No Subscriptions</b>\n\nYou haven't subscribed to any services yet.\nUse /subscribe to start monitoring appointment availability!",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    message = "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"

    for sub in subscriptions:
        service_info = get_service_info(sub["service_id"])
        if service_info:
            office_id = sub.get("office_id", "Unknown")
            message += f"• <b>{service_info['name']}</b>\n"
            message += f"   Service ID: {sub['service_id']}\n"
            message += f"   📍 Office ID: {office_id}\n"
            message += f"   📅 Subscribed: {sub['subscribed_at'][:10]}\n\n"

    message += f"<b>Total:</b> {len(subscriptions)} subscription(s)"

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
        [InlineKeyboardButton("📋 Subscribe to More", callback_data="subscribe")]
    )
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")
