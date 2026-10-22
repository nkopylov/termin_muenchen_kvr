# ABOUTME: Records every button press on a live alert or queued message (handler group -2).
# ABOUTME: Lets the checker leave a message alone while the user is working with it.

from telegram import Update
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import PendingRetireRepository, WatchRepository
from src.watches import when
from src.watches.alert_decision import INTERACTION_LOCK


async def record_interaction(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Mark the pressed message as in use; never answers the query, never stops other groups."""
    query = update.callback_query
    if query is None or query.message is None:
        return
    chat_id = query.message.chat.id
    message_id = query.message.message_id
    now = when.utcnow()
    with get_session() as session:
        WatchRepository(session).mark_interaction(chat_id, message_id, now)
        PendingRetireRepository(session).touch(
            chat_id, message_id, now + INTERACTION_LOCK
        )
