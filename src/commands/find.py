# ABOUTME: Find flow: popular services, browsing, office and time steps that create or change watches.
# ABOUTME: Entry points for /find, the reply keyboard's Find button and every "f1:" button.

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/find, /menu, /subscribe and the reply keyboard's Find button"""
    raise NotImplementedError


def build_find_screen(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    raise NotImplementedError


async def find_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "f1:" button"""
    raise NotImplementedError


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError


async def show_category_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: str, page: int
) -> None:
    raise NotImplementedError


async def show_service_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    raise NotImplementedError


async def show_when_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
    office_id: int | None,
) -> None:
    raise NotImplementedError
