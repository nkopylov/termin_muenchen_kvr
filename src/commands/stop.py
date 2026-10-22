"""
/stop command - Unsubscribe user and delete all subscriptions
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import SubscriptionRepository, UserRepository
from src.services.analytics_service import track_event

logger = logging.getLogger(__name__)


async def delete_user_data(bot, user_id: int, lang: str) -> None:
    """Finalize live messages and delete every row of the user"""
    raise NotImplementedError


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command"""
    user_id = update.effective_user.id
    # Read before the user row is deleted below
    lang = get_user_language(user_id, context)

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        # Get user info before deletion for analytics
        user = user_repo.get_user(user_id)
        days_since_registration = 0
        if user and user.subscribed_at:
            days_since_registration = (datetime.utcnow() - user.subscribed_at).days

        # Delete all subscriptions
        count = sub_repo.delete_all_user_subscriptions(user_id)

        # Delete user
        user_repo.delete_user(user_id)

    # Track user stopped
    await track_event(
        "user_stopped",
        user_id=user_id,
        days_since_registration=days_since_registration,
        total_subscriptions_at_stop=count,
    )

    await update.message.reply_text(t("stop.done", lang, count=count))
    logger.info(f"User {user_id} unsubscribed and removed {count} subscriptions")
