# ABOUTME: Buttons of messages sent before the watches UI; routes them to the current screens.
# ABOUTME: Registered last, so it also catches any callback no other handler took.

from telegram import Update
from telegram.ext import ContextTypes

from src.commands import find, watches
from src.handlers import text_input
from src.handlers.language_picker import client_language
from src.i18n import t
from src.i18n.user_language import get_stored_language, get_user_language
from src.services_manager import CATEGORY_KEYWORDS
from src.ui.screens import show_screen
from src.ui.telegram_safe import safe_answer, safe_edit_text
from src.watches import when

MY_WATCHES_DATA = (
    "myservices",
    "unsub_all",
    "unsub_all_confirm",
    "status",
    "setdates",
    "show_stats",
)
MY_WATCHES_PREFIXES = ("unsub:", "setdates:")


def _ids(args: list[str], count: int) -> list[int] | None:
    if len(args) != count or not all(a.isdigit() for a in args):
        return None
    return [int(a) for a in args]


async def _show_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_user_language(update.effective_user.id, context)
    text, markup = find.build_find_screen(lang)
    await show_screen(update, context, text, markup)


async def _show_my_watches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = get_user_language(user_id, context)
    if get_stored_language(user_id) is None:
        message = update.callback_query.message
        if message is not None:
            await safe_edit_text(
                context.bot,
                update.effective_chat.id,
                message.message_id,
                t("start.not_registered", client_language(update)),
            )
        return
    text, markup = watches.build_watches_screen(user_id, lang, when.utcnow())
    await show_screen(update, context, text, markup)


async def _show_category(update, context, args: list[str]) -> bool:
    category = args[0] if args else ""
    if len(args) == 1:
        page = 0
    elif len(args) == 2 and args[1].isdigit():
        page = int(args[1])
    else:
        return False
    if not category:
        return False
    if category in CATEGORY_KEYWORDS:
        await find.show_category_page(update, context, category, page)
    else:
        await find.show_categories(update, context)
    return True


async def _route(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> bool:
    """Shows the screen an old button leads to; False when it maps to none"""
    if data in MY_WATCHES_DATA or data.startswith(MY_WATCHES_PREFIXES):
        await _show_my_watches(update, context)
        return True

    name, _, rest = data.partition(":")
    args = rest.split(":") if rest else []
    if name == "cat" and len(args) == 1 or name == "catpage" and len(args) == 2:
        return await _show_category(update, context, args)
    if name in ("srv", "addsub") and (ids := _ids(args, 1)):
        await find.show_service_step(update, context, ids[0])
        return True
    if name == "selectoffice" and (ids := _ids(args, 2)):
        await find.show_when_step(update, context, ids[0], ids[1] or None)
        return True
    return False


async def legacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await safe_answer(query)
    text_input.clear_pending_input(context)
    if not await _route(update, context, query.data or ""):
        await _show_find(update, context)
