"""
/stop command - Unsubscribe user and delete all subscriptions
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository, SubscriptionRepository

logger = logging.getLogger(__name__)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        # Delete all subscriptions
        count = sub_repo.delete_all_user_subscriptions(user_id)

        # Delete user
        user_repo.delete_user(user_id)

    await update.message.reply_text(
        f"👋 You have been unsubscribed and {count} subscription(s) were removed.\n\n"
        "Use /start to register again."
    )
    logger.info(f"User {user_id} unsubscribed and removed {count} subscriptions")
