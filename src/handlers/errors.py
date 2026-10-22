# ABOUTME: Application error handler: logs unhandled exceptions of handlers and background tasks.
# ABOUTME: Also reports the error type to analytics.

import logging

from telegram.ext import ContextTypes

from src.services.analytics_service import track_event

logger = logging.getLogger(__name__)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error(f"Unhandled error while handling update {update!r}", exc_info=error)
    await track_event("handler_error", error_type=type(error).__name__)
