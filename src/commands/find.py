# ABOUTME: Find flow: popular services, browsing, office and time steps that create or change watches.
# ABOUTME: Entry points for /find, the reply keyboard's Find button and every "f1:" button.

import html
import math
from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src import services_manager
from src.database import get_session
from src.handlers.text_input import AWAIT_KEY, cancel_markup, clear_pending_input
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import (
    MAX_OPEN_WATCHES,
    LimitReached,
    UserRepository,
    WatchRecord,
    WatchRepository,
)
from src.services.immediate_check import (
    CHECKING_KEY,
    build_limit_screen,
    start_recheck,
    start_watch_check,
)
from src.services_manager import CATEGORY_KEYWORDS, categorize_services
from src.ui import callbacks as cb
from src.ui.screens import show_screen
from src.ui.telegram_safe import safe_answer, safe_edit_text, safe_send
from src.watches.availability import public_office_ids
from src.watches.labels import (
    POPULAR_SERVICE_IDS,
    office_label,
    service_label,
    watch_summary,
)
from src.watches.when import PRESETS, WhenSpec

POPULAR_EMOJI = {
    10339028: "🆘",
    10339027: "🎓",
    10502137: "💳",
    1063475: "🏠",
    1063441: "🆔",
    1063453: "🛂",
    1071896: "🪪",
    1064305: "🚗",
}
SERVICES_PER_PAGE = 10
MAX_OFFICES = 10
DATE_MODE_KINDS = {"b": "before", "r": "range"}


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _pairs(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def _lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return get_user_language(update.effective_user.id, context)


async def _ensure_registered(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    user_id = update.effective_user.id
    with get_session() as session:
        if UserRepository(session).get_user(user_id) is not None:
            return True
    text = t("find.not_registered", _lang(update, context))
    query = update.callback_query
    if query is not None and query.message is not None:
        await safe_edit_text(
            context.bot, query.message.chat_id, query.message.message_id, text
        )
    else:
        await safe_send(context.bot, update.effective_chat.id, text)
    return False


# S3 Find


def build_find_screen(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    popular = [
        _button(
            f"{POPULAR_EMOJI[sid]} {service_label(sid, lang)}", cb.find_service(sid)
        )
        for sid in POPULAR_SERVICE_IDS
        if services_manager.get_service_info(sid) is not None
    ]
    rows = _pairs(popular) + [[_button(t("find.btn_all", lang), cb.find_all())]]
    return t("find.title", lang), InlineKeyboardMarkup(rows)


async def _show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, markup = build_find_screen(_lang(update, context))
    await show_screen(update, context, text, markup)


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/find, /menu, /subscribe and the reply keyboard's Find button"""
    clear_pending_input(context)
    if await _ensure_registered(update, context):
        await _show_home(update, context)


# S5, S6 browse


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update, context)
    grouped = categorize_services()
    buttons = [
        _button(
            f"{t(f'categories.{cid}', lang)} ({len(grouped[cid])})",
            cb.find_category(cid, 0),
        )
        for cid in CATEGORY_KEYWORDS
        if grouped.get(cid)
    ]
    rows = _pairs(buttons) + [[_button(t("find.btn_back", lang), cb.find_home())]]
    await show_screen(
        update, context, t("find.categories", lang), InlineKeyboardMarkup(rows)
    )


async def show_category_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: str, page: int
) -> None:
    services = (
        categorize_services().get(category_id)
        if category_id in CATEGORY_KEYWORDS
        else None
    )
    if not services:
        await show_categories(update, context)
        return

    lang = _lang(update, context)
    pages = math.ceil(len(services) / SERVICES_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    first = page * SERVICES_PER_PAGE
    chunk = services[first : first + SERVICES_PER_PAGE]

    rows = [
        [_button(service_label(s["id"], lang), cb.find_service(s["id"]))] for s in chunk
    ]
    nav = []
    if page > 0:
        nav.append(
            _button(t("find.btn_prev", lang), cb.find_category(category_id, page - 1))
        )
    if page < pages - 1:
        nav.append(
            _button(t("find.btn_next", lang), cb.find_category(category_id, page + 1))
        )
    if nav:
        rows.append(nav)
    rows.append([_button(t("find.btn_back", lang), cb.find_all())])

    text = t(
        "find.category_page",
        lang,
        category=html.escape(t(f"categories.{category_id}", lang)),
        first=first + 1,
        last=first + len(chunk),
        total=len(services),
    )
    await show_screen(update, context, text, InlineKeyboardMarkup(rows))


# S7 office, S10 limit


def _service_available(service_id: int) -> bool:
    return services_manager.get_service_info(service_id) is not None and bool(
        public_office_ids(service_id)
    )


async def _show_unavailable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(update, context)
    markup = InlineKeyboardMarkup([[_button(t("find.btn_back", lang), cb.find_home())]])
    await show_screen(update, context, t("find.unavailable", lang), markup)


async def _show_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, markup = build_limit_screen(_lang(update, context))
    await show_screen(update, context, text, markup)


def _limit_blocks(user_id: int, service_id: int) -> bool:
    """True when watching this service would need a new open watch beyond the limit."""
    with get_session() as session:
        watches = WatchRepository(session)
        if watches.find_open(user_id, service_id) is not None:
            return False
        return watches.count_open(user_id) >= MAX_OPEN_WATCHES


async def show_service_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    if not _service_available(service_id):
        await _show_unavailable(update, context)
        return
    if _limit_blocks(update.effective_user.id, service_id):
        await _show_limit(update, context)
        return

    offices = public_office_ids(service_id)
    if len(offices) == 1:
        await show_when_step(update, context, service_id, None)
        return

    lang = _lang(update, context)
    labelled = sorted((office_label(oid, service_id, lang), oid) for oid in offices)[
        :MAX_OFFICES
    ]
    office_buttons = [
        _button(label, cb.find_office(service_id, oid)) for label, oid in labelled
    ]
    rows = (
        [[_button(t("find.btn_any_office", lang), cb.find_office(service_id, None))]]
        + _pairs(office_buttons)
        + [[_button(t("find.btn_back", lang), cb.find_home())]]
    )
    text = t("find.where", lang, service=html.escape(service_label(service_id, lang)))
    await show_screen(update, context, text, InlineKeyboardMarkup(rows))


# S8 when


def _when_markup(
    lang: str,
    preset_data: Callable[[str], str],
    date_data: Callable[[str], str],
    back_data: str,
) -> InlineKeyboardMarkup:
    presets = [
        _button(t(f"find.btn_{preset}", lang), preset_data(preset))
        for preset in cb.WHEN_PRESETS
    ]
    rows = _pairs(presets) + [
        [_button(t("find.btn_before", lang), date_data("b"))],
        [_button(t("find.btn_between", lang), date_data("r"))],
        [_button(t("find.btn_back", lang), back_data)],
    ]
    return InlineKeyboardMarkup(rows)


def _office_ok(service_id: int, office_id: int | None) -> bool:
    if not _service_available(service_id):
        return False
    return office_id is None or office_id in public_office_ids(service_id)


async def show_when_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
    office_id: int | None,
) -> None:
    if not _office_ok(service_id, office_id):
        await show_service_step(update, context, service_id)
        return

    lang = _lang(update, context)
    where = (
        t("watch.where_any", lang)
        if office_id is None
        else office_label(office_id, service_id, lang)
    )
    text = t(
        "find.when",
        lang,
        service=html.escape(service_label(service_id, lang)),
        where=html.escape(where),
    )
    with get_session() as session:
        existing = WatchRepository(session).find_open(
            update.effective_user.id, service_id
        )
    if existing is not None:
        text += "\n\n" + t("find.when_existing", lang)

    back = (
        cb.find_service(service_id)
        if len(public_office_ids(service_id)) > 1
        else cb.find_home()
    )
    markup = _when_markup(
        lang,
        lambda preset: cb.find_when(service_id, office_id, preset),
        lambda mode: cb.find_date(service_id, office_id, mode),
        back,
    )
    await show_screen(update, context, text, markup)


async def _show_edit_when(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rec: WatchRecord
) -> None:
    lang = _lang(update, context)
    text = t("find.when_edit", lang, summary=html.escape(watch_summary(rec, lang)))
    markup = _when_markup(
        lang,
        lambda preset: cb.find_edit_when(rec.id, preset),
        lambda mode: cb.find_edit_date(rec.id, mode),
        cb.watches_list(),
    )
    await show_screen(update, context, text, markup)


# f1: actions


def _own_watch(user_id: int, watch_id: int) -> WatchRecord | None:
    with get_session() as session:
        return WatchRepository(session).get_for_user(watch_id, user_id)


async def _switch_to_any_office(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int
) -> None:
    try:
        with get_session() as session:
            rec = WatchRepository(session).set_office(watch_id, None)
    except LimitReached:
        await _show_limit(update, context)
        return
    await _show_edit_when(update, context, rec)


async def _editable_watch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int
) -> WatchRecord | None:
    """The user's watch if its time can be changed as is; otherwise shows the right
    screen (an office no longer public switches the watch to any office) and returns None."""
    rec = _own_watch(update.effective_user.id, watch_id)
    if rec is None:
        await _show_home(update, context)
    elif not _service_available(rec.service_id):
        await _show_unavailable(update, context)
    elif rec.office_id is not None and rec.office_id not in public_office_ids(
        rec.service_id
    ):
        await _switch_to_any_office(update, context, rec.id)
    else:
        return rec
    return None


def _is_shown_live(rec: WatchRecord | None, message_id: int, when: WhenSpec) -> bool:
    """The pressed message already is this watch's live alert for the same time."""
    return (
        rec is not None
        and rec.status == "active"
        and rec.live is not None
        and rec.live.message_id == message_id
        and rec.when == when
    )


async def _on_preset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
    office_id: int | None,
    preset: str,
) -> None:
    if not _office_ok(service_id, office_id):
        await show_service_step(update, context, service_id)
        return
    user_id = update.effective_user.id
    pressed = update.callback_query.message.message_id
    when = PRESETS[preset]
    with get_session() as session:
        rec = WatchRepository(session).find_open(user_id, service_id)
    if context.user_data.get(CHECKING_KEY) == pressed or (
        _is_shown_live(rec, pressed, when) and rec.office_id == office_id
    ):
        return
    await start_watch_check(
        update,
        context,
        user_id,
        service_id,
        office_id,
        when,
        target_message_id=pressed,
    )


async def _on_edit_preset(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int, preset: str
) -> None:
    rec = await _editable_watch(update, context, watch_id)
    if rec is None:
        return
    pressed = update.callback_query.message.message_id
    when = PRESETS[preset]
    if context.user_data.get(CHECKING_KEY) == pressed or _is_shown_live(
        rec, pressed, when
    ):
        return
    await start_recheck(update, context, watch_id, when, target_message_id=pressed)


async def _on_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int
) -> None:
    user_id = update.effective_user.id
    rec = await _editable_watch(update, context, watch_id)
    if rec is None:
        return
    if not rec.is_open and _limit_blocks(user_id, rec.service_id):
        await _show_limit(update, context)
    else:
        await _show_edit_when(update, context, rec)


async def _on_any_office(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int
) -> None:
    rec = _own_watch(update.effective_user.id, watch_id)
    if rec is None:
        await _show_home(update, context)
    elif not _service_available(rec.service_id):
        await _show_unavailable(update, context)
    else:
        await _switch_to_any_office(update, context, rec.id)


async def _ask_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    service_id: int,
    office_id: int | None,
    watch_id: int | None,
) -> None:
    lang = _lang(update, context)
    kind = DATE_MODE_KINDS[mode]
    key = "find.ask_before" if kind == "before" else "find.ask_range"
    message = await show_screen(update, context, t(key, lang), cancel_markup(lang))
    context.user_data[AWAIT_KEY] = {
        "kind": kind,
        "service_id": service_id,
        "office_id": office_id,
        "watch_id": watch_id,
        "prompt_msg_id": None if message is None else message.message_id,
    }


async def _on_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
    office_id: int | None,
    mode: str,
) -> None:
    if not _office_ok(service_id, office_id):
        await show_service_step(update, context, service_id)
        return
    await _ask_date(update, context, mode, service_id, office_id, None)


async def _on_edit_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, watch_id: int, mode: str
) -> None:
    rec = await _editable_watch(update, context, watch_id)
    if rec is None:
        return
    await _ask_date(update, context, mode, rec.service_id, rec.office_id, rec.id)


async def _on_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict | None
) -> None:
    if pending is None:
        await _show_home(update, context)
        return
    if pending.get("watch_id") is not None:
        rec = _own_watch(update.effective_user.id, pending["watch_id"])
        if rec is None:
            await _show_home(update, context)
        else:
            await _show_edit_when(update, context, rec)
        return
    await show_when_step(update, context, pending["service_id"], pending["office_id"])


async def find_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every "f1:" button"""
    query = update.callback_query
    await safe_answer(query)
    pending = context.user_data.pop(AWAIT_KEY, None)
    if not await _ensure_registered(update, context):
        return

    data = cb.parse(query.data or "")
    if data is None or data.scope != "f1":
        await _show_home(update, context)
        return

    args = data.args
    match data.action:
        case "all":
            await show_categories(update, context)
        case "cat":
            await show_category_page(update, context, *args)
        case "svc":
            await show_service_step(update, context, *args)
        case "off":
            await show_when_step(update, context, args[0], args[1] or None)
        case "when":
            await _on_preset(update, context, args[0], args[1] or None, args[2])
        case "date":
            await _on_date(update, context, args[0], args[1] or None, args[2])
        case "edit":
            await _on_edit(update, context, *args)
        case "ewhen":
            await _on_edit_preset(update, context, *args)
        case "edate":
            await _on_edit_date(update, context, *args)
        case "any":
            await _on_any_office(update, context, *args)
        case "x":
            await _on_cancel(update, context, pending)
        case _:
            await _show_home(update, context)
