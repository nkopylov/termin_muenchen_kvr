"""
Button callback handlers for Telegram inline keyboards.
Handles all button interactions including menus, service subscription, and navigation.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository, SubscriptionRepository
from src.services_manager import (
    categorize_services,
    get_service_info,
    get_category_for_service,
)
from src.services.appointment_checker import get_stats, get_user_date_range
from src.config import get_config

logger = logging.getLogger(__name__)


async def show_main_menu(query, user_id: int):
    """Show main menu as inline message"""
    menu_text = "🏠 <b>Main Menu</b>\n\nChoose an action:"

    keyboard = [
        [InlineKeyboardButton("📋 Subscribe to Services", callback_data="categories")],
        [InlineKeyboardButton("📊 My Subscriptions", callback_data="myservices")],
        [InlineKeyboardButton("📅 Set Date Range", callback_data="setdates")],
        [InlineKeyboardButton("ℹ️ Subscription Status", callback_data="status")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        menu_text, reply_markup=reply_markup, parse_mode="HTML"
    )


async def show_stats_inline(query):
    """Show bot statistics inline"""
    stats = get_stats()

    with get_session() as session:
        user_repo = UserRepository(session)
        total_users = len(user_repo.get_all_users())

    success_rate = 0
    if stats["total_checks"] > 0:
        success_rate = (stats["successful_checks"] / stats["total_checks"]) * 100

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

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_status_inline(query, user_id: int):
    """Show user's status inline"""
    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ You are not registered.\n\nUse /start to register.",
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return

        subs = sub_repo.get_user_subscriptions(user_id)
        total_users = len(user_repo.get_all_users())
        user_language = user.language
        num_subs = len(subs)

    start_date, end_date = get_user_date_range(user_id)

    message = (
        "📊 <b>Your Status</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📋 Subscriptions: <b>{num_subs}</b>\n"
        f"📅 Date Range: {start_date} to {end_date}\n"
        f"🌐 Language: {user_language}\n\n"
        f"👥 Total Users: <b>{total_users}</b>\n\n"
        f"⏱ Check Interval: {get_config().check_interval} seconds"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_setdates_inline(query, user_id: int):
    """Show instructions for setting date range"""
    start_date, end_date = get_user_date_range(user_id)

    message = (
        "📅 <b>Set Date Range</b>\n\n"
        f"Current range: <b>{start_date}</b> to <b>{end_date}</b>\n\n"
        "To change your date range, use the command:\n"
        "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
        "<b>Example:</b>\n"
        "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
        "This sets the date range for appointment searches."
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_category_services(query, category_name: str, page: int = 0):
    """Show services in a category"""
    categories = categorize_services()
    services = categories.get(category_name, [])

    if not services:
        await query.edit_message_text(
            f"❌ No services found in {category_name} category."
        )
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
        name = service["name"]
        if len(name) > 50:
            name = name[:47] + "..."

        keyboard.append(
            [InlineKeyboardButton(name, callback_data=f"srv:{service['id']}")]
        )

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                "◀️ Previous", callback_data=f"catpage:{category_name}:{page-1}"
            )
        )
    nav_row.append(InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu"))
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                "Next ▶️", callback_data=f"catpage:{category_name}:{page+1}"
            )
        )
    keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    pagination_text = f"Showing {start_idx + 1}-{end_idx} of {len(services)} services"

    try:
        await query.edit_message_text(
            f"<b>{category_name}</b>\n\n{pagination_text}",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        # Ignore "message is not modified" errors
        if "message is not modified" not in str(e).lower():
            raise


async def show_service_details(query, service_id: int, user_id: int):
    """Show service details and subscribe button"""
    service_info = get_service_info(service_id)

    if not service_info:
        await query.edit_message_text("❌ Service not found.")
        return

    # Check if already subscribed
    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        user_subs = sub_repo.get_user_subscriptions(user_id)

    is_subscribed = any(sub["service_id"] == service_id for sub in user_subs)

    # Build message
    message = (
        f"<b>{service_info['name']}</b>\n\n"
        f"Service ID: <code>{service_info['id']}</code>\n"
    )

    if service_info.get("maxQuantity"):
        message += f"Max. Quantity: {service_info['maxQuantity']}\n"

    message += f"\nStatus: {'✅ Subscribed' if is_subscribed else '⭕ Not subscribed'}"

    # Build keyboard
    keyboard = []
    if is_subscribed:
        keyboard.append(
            [InlineKeyboardButton("🗑 Unsubscribe", callback_data=f"unsub:{service_id}")]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton("✅ Subscribe", callback_data=f"addsub:{service_id}")]
        )

    # Back button
    category = get_category_for_service(service_id)
    if category:
        keyboard.append(
            [InlineKeyboardButton("◀️ Back", callback_data=f"cat:{category}")]
        )
    keyboard.append([InlineKeyboardButton("🏠 Categories", callback_data="categories")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_office_selection(query, service_id: int, user_id: int):
    """Show office selection for a service subscription"""
    from src.services_manager import get_offices_for_service

    service_info = get_service_info(service_id)
    if not service_info:
        await query.edit_message_text("❌ Service not found.")
        return

    # Get all offices that support this service
    offices = get_offices_for_service(service_id)

    if not offices:
        await query.edit_message_text(
            f"❌ No offices found for '{service_info['name']}'.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("◀️ Back", callback_data=f"srv:{service_id}")]]
            ),
        )
        return

    # Build message
    message = (
        f"<b>{service_info['name']}</b>\n\n"
        f"📍 Please select an office:\n"
        f"({len(offices)} available)"
    )

    # Build keyboard with office options (max 10 per page for now)
    keyboard = []
    for office in offices[:20]:  # Show first 20 offices
        office_name = office.get("name", f"Office {office['id']}")
        # Shorten long names
        if len(office_name) > 45:
            office_name = office_name[:42] + "..."

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📍 {office_name}",
                    callback_data=f"selectoffice:{service_id}:{office['id']}",
                )
            ]
        )

    # Add note if there are more offices
    if len(offices) > 20:
        message += f"\n\n⚠️ Only the first 20 of {len(offices)} offices are shown."

    # Back button
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data=f"srv:{service_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_myservices(query, user_id: int):
    """Show user's subscriptions inline"""
    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📋 <b>No Subscriptions</b>\n\nYou haven't subscribed to any services yet.\nUse /subscribe to start monitoring appointment availability!",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    message = "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"

    for sub in subscriptions:
        service_info = get_service_info(sub["service_id"])
        if service_info:
            # Add office information
            office_id = sub.get("office_id", "Unknown")
            message += f"• <b>{service_info['name']}</b>\n"
            message += f"   Service ID: {sub['service_id']}\n"
            message += f"   📍 Office ID: {office_id}\n"
            message += f"   📅 Subscribed: {sub['subscribed_at'][:10]}\n\n"

    message += f"<b>Total:</b> {len(subscriptions)} subscription(s)"

    # Add navigation buttons
    keyboard = []
    if len(subscriptions) <= 10:
        for sub in subscriptions:
            service_info = get_service_info(sub["service_id"])
            if service_info:
                name = service_info["name"]
                if len(name) > 40:
                    name = name[:37] + "..."
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🗑 {name}", callback_data=f"unsub:{sub['service_id']}"
                        )
                    ]
                )

    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    # Check for orphaned booking sessions (bot restarted during booking)
    from src.services.queue_manager import is_user_in_queue

    if is_user_in_queue(user_id) and (
        data.startswith("time_") or data == "cancel_booking"
    ):
        # User has an active booking session but ConversationHandler doesn't know about it
        from src.commands.booking import delete_booking_session

        delete_booking_session(user_id)
        await query.edit_message_text(
            "❌ Your booking session was interrupted (bot restarted).\n\n"
            "Please start a new booking from an appointment notification."
        )
        return

    # Handle main menu
    if data == "main_menu":
        await show_main_menu(query, user_id)
        return

    # Handle menu actions
    if data == "show_stats":
        await show_stats_inline(query)
        return

    if data == "myservices":
        await show_myservices(query, user_id)
        return

    if data == "status":
        await show_status_inline(query, user_id)
        return

    if data == "setdates":
        await show_setdates_inline(query, user_id)
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
                    row.append(
                        InlineKeyboardButton(
                            f"{category} ({len(services)})",
                            callback_data=f"cat:{category}",
                        )
                    )
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📋 <b>Select a Category:</b>", reply_markup=reply_markup, parse_mode="HTML"
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
        # Show office selection for subscription
        service_id = int(data[7:])
        await show_office_selection(query, service_id, user_id)

    elif data.startswith("selectoffice:"):
        # User selected an office - add subscription
        parts = data.split(":")
        service_id = int(parts[1])
        office_id = int(parts[2])

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            success = sub_repo.add_subscription(
                user_id, service_id, office_id=office_id
            )

        if success:
            await query.answer("✅ Subscribed!", show_alert=True)
            await show_service_details(query, service_id, user_id)
        else:
            await query.answer("❌ Subscription failed", show_alert=True)

    elif data.startswith("unsub:"):
        # Remove subscription
        service_id = int(data[6:])

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            sub_repo.remove_subscription(user_id, service_id)

        await query.answer("🗑 Unsubscribed", show_alert=True)
        await show_service_details(query, service_id, user_id)
