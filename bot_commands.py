"""
Telegram bot command handlers with button-based interface
Refactored to use new architecture with repositories and type safety
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# New architecture imports
from database import get_session
from repositories import UserRepository, SubscriptionRepository
from models import Language, Intent
from i18n import _, TranslationKey

# Old modules (still used)
from services_manager import categorize_services, get_service_info, get_category_for_service, get_default_office_for_service
from ai_assistant import parse_user_request, get_official_information, enhance_service_info
from i18n import translate_text, LANGUAGE_INFO
from config import get_config

logger = logging.getLogger(__name__)


async def show_main_menu(query, user_id: int):
    """Show main menu as inline message"""
    with get_session() as session:
        user_repo = UserRepository(session)
        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)

    config = get_config()
    has_ai = config.has_openai

    # Build menu message
    menu_text = "🏠 <b>Main Menu</b>\n\nChoose an action:"

    # Build keyboard with main actions
    keyboard = [
        [InlineKeyboardButton("📋 Subscribe to Services", callback_data="categories")],
        [InlineKeyboardButton("📊 My Subscriptions", callback_data="myservices")],
    ]

    if has_ai:
        keyboard.append([InlineKeyboardButton("🤖 AI Assistant", callback_data="ask_help")])

    keyboard.extend([
        [InlineKeyboardButton("🌐 Change Language", callback_data="change_language")],
        [InlineKeyboardButton("📈 Bot Statistics", callback_data="show_stats")],
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='HTML')


async def show_stats_inline(query):
    """Show bot statistics inline"""
    from telegram_bot import stats

    with get_session() as session:
        user_repo = UserRepository(session)
        total_users = len(user_repo.get_all_users())

    success_rate = 0
    if stats['total_checks'] > 0:
        success_rate = (stats['successful_checks'] / stats['total_checks']) * 100

    message = (
        "📈 <b>Bot Statistics</b>\n\n"
        f"👥 Users: {total_users}\n"
        f"🔍 Total checks: {stats['total_checks']}\n"
        f"✅ Successful: {stats['successful_checks']}\n"
        f"❌ Failed: {stats['failed_checks']}\n"
        f"📊 Success rate: {success_rate:.1f}%\n"
        f"🎯 Appointments found: {stats['appointments_found_count']}"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with action buttons"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            # Not registered, redirect to /start
            await update.message.reply_text(
                "👋 Welcome! Please use /start to register first.",
                parse_mode='HTML'
            )
            return

        lang_code = user.language
        lang = Language(lang_code)

    config = get_config()
    has_ai = config.has_openai

    # Build menu message
    menu_text = "🏠 <b>Main Menu</b>\n\nChoose an action:"

    # Build keyboard with main actions
    keyboard = [
        [InlineKeyboardButton("📋 Subscribe to Services", callback_data="categories")],
        [InlineKeyboardButton("📊 My Subscriptions", callback_data="myservices")],
    ]

    if has_ai:
        keyboard.append([InlineKeyboardButton("🤖 AI Assistant", callback_data="ask_help")])

    keyboard.extend([
        [InlineKeyboardButton("🌐 Change Language", callback_data="change_language")],
        [InlineKeyboardButton("📈 Bot Statistics", callback_data="show_stats")],
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='HTML')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command - show language selection first, then welcome"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    with get_session() as session:
        user_repo = UserRepository(session)
        user = user_repo.get_user(user_id)

        if not user:
            # New user - create with default date range
            today = datetime.now()
            end_date = today + timedelta(days=180)
            user_repo.create_user(
                user_id=user_id,
                username=username,
                language="de",
                start_date=today.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            # Show language selection for new users
            await show_language_selection(update, context)
        else:
            # Existing user - show welcome in their language
            lang = Language(user.language)
            welcome_msg = _(TranslationKey.WELCOME, lang)

            # Add menu button
            keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                welcome_msg,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )


async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """Show language selection keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang:de"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")
        ],
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "🌐 <b>Choose your language / Wählen Sie Ihre Sprache / Выберите язык</b>"

    if query:
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /language command - change language"""
    await show_language_selection(update, context)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category selection"""
    categories = categorize_services()

    # Create category buttons (2 per row)
    keyboard = []
    cat_items = list(categories.items())

    for i in range(0, len(cat_items), 2):
        row = []
        for j in range(2):
            if i + j < len(cat_items):
                category, services = cat_items[i + j]
                row.append(InlineKeyboardButton(
                    f"{category} ({len(services)})",
                    callback_data=f"cat:{category}"
                ))
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)

    await update.message.reply_text(
        _(TranslationKey.SELECT_CATEGORY, lang),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def show_category_services(query, category_name: str, page: int = 0):
    """Show services in a category"""
    categories = categorize_services()
    services = categories.get(category_name, [])

    user_id = query.from_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)

    if not services:
        await query.edit_message_text(_(TranslationKey.NO_SERVICES_IN_CATEGORY, lang))
        return

    # Show max 10 services per page
    services_per_page = 10
    total_pages = (len(services) + services_per_page - 1) // services_per_page

    start_idx = page * services_per_page
    end_idx = min(start_idx + services_per_page, len(services))
    page_services = services[start_idx:end_idx]

    keyboard = []
    for service in page_services:
        # Truncate long names
        name = service['name']
        if len(name) > 50:
            name = name[:47] + "..."

        keyboard.append([InlineKeyboardButton(
            name,
            callback_data=f"srv:{service['id']}"
        )])

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Zurück", callback_data=f"catpage:{category_name}:{page-1}"))
    nav_row.append(InlineKeyboardButton("🏠 Kategorien", callback_data="categories"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Weiter ▶️", callback_data=f"catpage:{category_name}:{page+1}"))
    keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    pagination_text = _(
        TranslationKey.SERVICES_PAGINATION,
        lang,
        start=start_idx + 1,
        end=end_idx,
        total=len(services)
    )

    try:
        await query.edit_message_text(
            f"<b>{category_name}</b>\n\n{pagination_text}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception as e:
        # Ignore "message is not modified" errors
        if "message is not modified" not in str(e).lower():
            raise


async def show_service_details(query, service_id: int, user_id: int):
    """Show service details and subscribe button"""
    service_info = get_service_info(service_id)

    if not service_info:
        await query.edit_message_text("❌ Dienst nicht gefunden.")
        return

    # Check if already subscribed
    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        user_subs = sub_repo.get_user_subscriptions(user_id)

    is_subscribed = any(sub['service_id'] == service_id for sub in user_subs)

    # Build message
    message = (
        f"<b>{service_info['name']}</b>\n\n"
        f"Service ID: <code>{service_info['id']}</code>\n"
    )

    if service_info.get('maxQuantity'):
        message += f"Max. Anzahl: {service_info['maxQuantity']}\n"

    message += f"\nStatus: {'✅ Abonniert' if is_subscribed else '⭕ Nicht abonniert'}"

    # Build keyboard
    keyboard = []
    if is_subscribed:
        keyboard.append([InlineKeyboardButton(
            "🗑 Abonnement kündigen",
            callback_data=f"unsub:{service_id}"
        )])
    else:
        keyboard.append([InlineKeyboardButton(
            "✅ Abonnieren",
            callback_data=f"addsub:{service_id}"
        )])

    # Back button
    category = get_category_for_service(service_id)
    if category:
        keyboard.append([InlineKeyboardButton("◀️ Zurück", callback_data=f"cat:{category}")])
    keyboard.append([InlineKeyboardButton("🏠 Kategorien", callback_data="categories")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    # Handle main menu
    if data == "main_menu":
        await show_main_menu(query, user_id)
        return

    # Handle menu actions
    if data == "change_language":
        await show_language_selection(None, None, query)
        return

    if data == "ask_help":
        with get_session() as session:
            user_repo = UserRepository(session)
            lang_code = user_repo.get_user_language(user_id)
            lang = Language(lang_code)

        await query.edit_message_text(
            _(TranslationKey.ASK_HELP, lang),
            parse_mode='HTML'
        )
        return

    if data == "show_stats":
        await show_stats_inline(query)
        return

    if data == "myservices":
        await show_myservices(query, user_id)
        return

    # Handle language selection
    if data.startswith("lang:"):
        lang_code = data[5:]

        with get_session() as session:
            user_repo = UserRepository(session)
            user_repo.set_user_language(user_id, lang_code)

        lang = Language(lang_code)

        # Show confirmation and welcome message
        await query.answer(_(TranslationKey.LANGUAGE_CHANGED, lang), show_alert=True)
        await query.edit_message_text(
            _(TranslationKey.WELCOME, lang),
            parse_mode='HTML'
        )
        return

    # Handle translation requests
    if data.startswith("translate:"):
        parts = data.split(":")
        target_lang = parts[1]
        message_id = parts[2] if len(parts) > 2 else None

        # Get original message text
        original_text = query.message.text_html

        # Remove existing disclaimer if present
        for lang in ['de', 'en', 'ru']:
            disclaimer = get_message('translation_disclaimer', lang)
            original_text = original_text.replace(disclaimer, '')

        # Translate
        translated = await translate_text(original_text, target_lang)
        translated += get_message('translation_disclaimer', target_lang)

        # Update message with translation
        # Keep translate buttons for other languages
        keyboard = []
        for lang_enum in Language:
            lang_code = lang_enum.value
            if lang_code != target_lang:
                lang_info = LANGUAGE_INFO[lang_enum]
                button_text = f"{lang_info['flag']} Translate to {lang_info['name']}"
                keyboard.append([InlineKeyboardButton(
                    button_text,
                    callback_data=f"translate:{lang_code}:{message_id}"
                )])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await query.edit_message_text(translated, reply_markup=reply_markup, parse_mode='HTML')
        return

    if data == "categories":
        # Show all categories
        categories = categorize_services()
        keyboard = []
        cat_items = list(categories.items())

        for i in range(0, len(cat_items), 2):
            row = []
            for j in range(2):
                if i + j < len(cat_items):
                    category, services = cat_items[i + j]
                    row.append(InlineKeyboardButton(
                        f"{category} ({len(services)})",
                        callback_data=f"cat:{category}"
                    ))
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📋 <b>Kategorie auswählen:</b>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif data.startswith("cat:"):
        # Show services in category
        category = data[4:]
        await show_category_services(query, category)

    elif data.startswith("catpage:"):
        # Paginated category view
        parts = data.split(":")
        category = parts[1]
        page = int(parts[2])
        await show_category_services(query, category, page)

    elif data.startswith("srv:"):
        # Show service details
        service_id = int(data[4:])
        await show_service_details(query, service_id, user_id)

    elif data.startswith("addsub:"):
        # Add subscription
        service_id = int(data[7:])

        # Get the appropriate office for this service
        office_id = get_default_office_for_service(service_id)
        if not office_id:
            await query.answer("❌ Keine passende Behörde gefunden", show_alert=True)
            return

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            success = sub_repo.add_subscription(user_id, service_id, office_id=office_id)

        if success:
            await query.answer("✅ Abonniert!", show_alert=True)
            await show_service_details(query, service_id, user_id)
        else:
            await query.answer("❌ Fehler beim Abonnieren", show_alert=True)

    elif data.startswith("unsub:"):
        # Remove subscription
        service_id = int(data[6:])

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            sub_repo.remove_subscription(user_id, service_id)

        await query.answer("🗑 Abonnement gekündigt", show_alert=True)
        await show_service_details(query, service_id, user_id)


async def show_myservices(query, user_id: int):
    """Show user's subscriptions inline"""
    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            _(TranslationKey.NO_SUBSCRIPTIONS, lang),
            reply_markup=reply_markup
        )
        return

    message = _(TranslationKey.MY_SUBSCRIPTIONS, lang)

    for sub in subscriptions:
        service_info = get_service_info(sub['service_id'])
        if service_info:
            item_text = _(
                TranslationKey.SERVICE_SUBSCRIPTION_ITEM,
                lang,
                name=service_info['name'],
                id=sub['service_id'],
                date=sub['subscribed_at'][:10]  # Extract date from ISO format
            )
            message += f"{item_text}\n\n"

    message += _(TranslationKey.TOTAL_SUBSCRIPTIONS, lang, count=len(subscriptions))

    # Add navigation buttons
    keyboard = []
    if len(subscriptions) <= 10:
        for sub in subscriptions:
            service_info = get_service_info(sub['service_id'])
            if service_info:
                name = service_info['name']
                if len(name) > 40:
                    name = name[:37] + "..."
                keyboard.append([InlineKeyboardButton(
                    f"🗑 {name}",
                    callback_data=f"unsub:{sub['service_id']}"
                )])

    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')


async def myservices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's active subscriptions"""
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        await update.message.reply_text(
            _(TranslationKey.NO_SUBSCRIPTIONS, lang)
        )
        return

    message = _(TranslationKey.MY_SUBSCRIPTIONS, lang)

    for sub in subscriptions:
        service_info = get_service_info(sub['service_id'])
        if service_info:
            item_text = _(
                TranslationKey.SERVICE_SUBSCRIPTION_ITEM,
                lang,
                name=service_info['name'],
                id=sub['service_id'],
                date=sub['subscribed_at'][:10]  # Extract date from ISO format
            )
            message += f"{item_text}\n\n"

    message += _(TranslationKey.TOTAL_SUBSCRIPTIONS, lang, count=len(subscriptions))

    # Add unsubscribe buttons
    if len(subscriptions) <= 10:
        keyboard = []
        for sub in subscriptions:
            service_info = get_service_info(sub['service_id'])
            if service_info:
                name = service_info['name']
                if len(name) > 30:
                    name = name[:27] + "..."
                keyboard.append([InlineKeyboardButton(
                    f"🗑 {name}",
                    callback_data=f"unsub:{sub['service_id']}"
                )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message, parse_mode='HTML')


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    AI-powered command to understand freeform user requests
    Usage: /ask Ich brauche einen neuen Personalausweis
    """
    user_id = update.effective_user.id

    with get_session() as session:
        user_repo = UserRepository(session)
        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)

    if not context.args:
        await update.message.reply_text(
            _(TranslationKey.ASK_HELP, lang),
            parse_mode='HTML'
        )
        return

    user_query = ' '.join(context.args)

    # Show typing indicator
    await update.message.chat.send_action(action="typing")

    logger.info(f"AI request from user {user_id}: {user_query}")

    # Parse request with AI
    result = parse_user_request(user_query, max_suggestions=5, user_language=lang)

    if result.intent == Intent.INFORMATION_REQUEST:
        # User is asking for information, not looking for a service
        # Detect query language and use it for the response
        query_lang = lang  # Default to user's preference

        # Simple language detection based on character sets
        if any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in user_query):
            query_lang = Language.RU  # Cyrillic detected

        await update.message.reply_text(
            _(TranslationKey.PROCESSING_QUESTION, query_lang),
            parse_mode='HTML'
        )

        answer = get_official_information(user_query, user_language=query_lang)

        if answer:
            message = _(TranslationKey.INFORMATION_HEADER, query_lang)
            message += f"{answer}\n\n"
            message += _(TranslationKey.MORE_QUESTIONS, query_lang)

            # AI already responds in user's language, no translation needed
            await update.message.reply_text(message, parse_mode='HTML')
        else:
            await update.message.reply_text(
                _(TranslationKey.NO_ANSWER_FOUND, lang),
                parse_mode='HTML'
            )

    else:
        # Service search - suggest matching services
        suggested_ids = result.suggested_services

        if not suggested_ids:
            await update.message.reply_text(
                _(TranslationKey.NO_MATCHING_SERVICES, lang),
                parse_mode='HTML'
            )
            return

        # Build message with suggested services
        message = _(TranslationKey.MATCHING_SERVICES_FOUND, lang)

        if result.explanation:
            message += f"<i>{result.explanation}</i>\n\n"

        # Create keyboard with service buttons
        keyboard = []
        for service_id in suggested_ids:
            service_info = get_service_info(service_id)
            if service_info:
                name = service_info['name']
                if len(name) > 45:
                    name = name[:42] + "..."

                message += f"📋 {service_info['name']}\n"

                keyboard.append([InlineKeyboardButton(
                    f"✅ {name}",
                    callback_data=f"srv:{service_id}"
                )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        message += _(TranslationKey.TAP_SERVICE_DETAILS, lang)

        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def enhanced_service_details(query, service_id: int, user_id: int):
    """Show service details with AI-enhanced information"""
    service_info = get_service_info(service_id)

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        lang_code = user_repo.get_user_language(user_id)
        lang = Language(lang_code)
        user_subs = sub_repo.get_user_subscriptions(user_id)

    if not service_info:
        await query.edit_message_text(_(TranslationKey.SERVICE_NOT_FOUND, lang))
        return

    # Check if already subscribed
    is_subscribed = any(sub.service_id == service_id for sub in user_subs)

    # Build message
    message = f"<b>{service_info['name']}</b>\n\n"

    # Get AI-enhanced description
    enhanced_info = enhance_service_info(service_id, user_language=lang)
    if enhanced_info:
        message += f"ℹ️ <i>{enhanced_info}</i>\n\n"

    message += f"Service ID: <code>{service_info['id']}</code>\n"

    if service_info.get('maxQuantity'):
        message += f"Max. Anzahl: {service_info['maxQuantity']}\n"

    message += f"\nStatus: {'✅ Abonniert' if is_subscribed else '⭕ Nicht abonniert'}"

    # Build keyboard
    keyboard = []
    if is_subscribed:
        keyboard.append([InlineKeyboardButton(
            "🗑 Abonnement kündigen",
            callback_data=f"unsub:{service_id}"
        )])
    else:
        keyboard.append([InlineKeyboardButton(
            "✅ Abonnieren",
            callback_data=f"addsub:{service_id}"
        )])

    # Back button
    category = get_category_for_service(service_id)
    if category:
        keyboard.append([InlineKeyboardButton("◀️ Zurück", callback_data=f"cat:{category}")])
    keyboard.append([InlineKeyboardButton("🏠 Kategorien", callback_data="categories")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
