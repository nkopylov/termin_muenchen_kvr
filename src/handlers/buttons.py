"""
Button callback handlers for Telegram inline keyboards.
Handles all button interactions including menus, service subscription, and navigation.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database import get_session
from src.repositories import UserRepository, SubscriptionRepository
from src.services_manager import (
    categorize_services,
    get_service_info,
    get_category_for_service,
    get_office_name,
)
from src.services.appointment_checker import get_stats, get_user_date_range
from src.config import get_config
from src.services.analytics_service import track_event


async def show_main_menu(query, user_id: int):
    """Show main menu as inline message"""
    menu_text = "🏠 <b>Main Menu</b>\n\nChoose an action:"

    keyboard = [
        [
            InlineKeyboardButton(
                "📋 Subscribe to available Termins", callback_data="categories"
            )
        ],
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
    from src.repositories import AppointmentLogRepository
    from datetime import datetime

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        log_repo = AppointmentLogRepository(session)

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

        # Get user-specific appointment stats
        user_sub_service_ids = [sub["service_id"] for sub in subs]
        all_logs = log_repo.get_all_logs()
        user_appointments = [
            log for log in all_logs if log["service_id"] in user_sub_service_ids
        ]

    start_date, end_date = get_user_date_range(user_id)

    # Get global stats for timing info
    stats = get_stats()
    last_check = stats.get("last_check_time")
    check_interval = get_config().check_interval

    # Calculate time since last check
    if last_check:
        time_since_check = (datetime.now() - last_check).total_seconds()
        if time_since_check < 60:
            last_check_str = f"{int(time_since_check)} seconds ago"
        elif time_since_check < 3600:
            last_check_str = f"{int(time_since_check / 60)} minutes ago"
        else:
            last_check_str = f"{int(time_since_check / 3600)} hours ago"

        # Calculate next check estimate
        next_check_seconds = max(0, check_interval - time_since_check)
        if next_check_seconds < 60:
            next_check_str = f"~{int(next_check_seconds)} seconds"
        else:
            next_check_str = f"~{int(next_check_seconds / 60)} minutes"
    else:
        last_check_str = "Never"
        next_check_str = "Soon"

    # User-specific appointment stats
    user_appointments_count = len(user_appointments)
    if user_appointments and user_appointments_count > 0:
        latest_appointment = user_appointments[0]
        latest_time = latest_appointment.get("found_at", "")
        if latest_time:
            try:
                latest_dt = datetime.fromisoformat(latest_time)
                days_ago = (datetime.now() - latest_dt).days
                if days_ago == 0:
                    latest_str = "today"
                elif days_ago == 1:
                    latest_str = "yesterday"
                else:
                    latest_str = f"{days_ago} days ago"
            except (ValueError, TypeError):
                latest_str = "recently"
        else:
            latest_str = "recently"
        stats_line = (
            f"\n🎯 Appointments found: {user_appointments_count} (last: {latest_str})"
        )
    else:
        stats_line = "\n🎯 Appointments found: 0"

    message = (
        "📊 <b>Your Status</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📋 Subscriptions: <b>{num_subs}</b>\n"
        f"📅 Date Range: {start_date} to {end_date}\n"
        f"🌐 Language: {user_language}\n\n"
        f"🔍 Last checked: {last_check_str}\n"
        f"⏱ Next check in: {next_check_str}\n"
        f"⚙️ Check interval: {check_interval} seconds"
        f"{stats_line}\n\n"
        f"👥 Total Users: <b>{total_users}</b>"
    )

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_setdates_inline(query, user_id: int):
    """Show instructions for setting date range"""
    from datetime import datetime, timedelta

    start_date, end_date = get_user_date_range(user_id)

    # Calculate preset dates
    today = datetime.now()
    date_2 = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    date_7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    date_30 = (today + timedelta(days=30)).strftime("%Y-%m-%d")
    date_90 = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    date_180 = (today + timedelta(days=180)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    message = (
        "📅 <b>Set Date Range</b>\n\n"
        f"Current range: <b>{start_date}</b> to <b>{end_date}</b>\n\n"
        "Choose a preset or use a custom range:\n\n"
        "<b>Custom Range:</b>\n"
        "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
        "<b>Example:</b> <code>/setdates 2025-10-01 2025-10-31</code>"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                f"📅 Next 2 days ({today_str} to {date_2})",
                callback_data="setdates:2",
            )
        ],
        [
            InlineKeyboardButton(
                f"📅 Next week ({today_str} to {date_7})",
                callback_data="setdates:7",
            )
        ],
        [
            InlineKeyboardButton(
                f"📅 Next 30 days ({today_str} to {date_30})",
                callback_data="setdates:30",
            )
        ],
        [
            InlineKeyboardButton(
                f"📅 Next 3 months ({today_str} to {date_90})",
                callback_data="setdates:90",
            )
        ],
        [
            InlineKeyboardButton(
                f"📅 Next 6 months ({today_str} to {date_180})",
                callback_data="setdates:180",
            )
        ],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]
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
            office_id = sub.get("office_id")
            office_name = get_office_name(office_id) if office_id else "Unknown Office"
            message += f"• <b>{service_info['name']}</b>\n"
            message += f"   📍 {office_name}\n"
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

    if len(subscriptions) > 0:
        keyboard.append(
            [InlineKeyboardButton("🗑 Unsubscribe from All", callback_data="unsub_all")]
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

    if data.startswith("setdates:"):
        # Handle preset date ranges
        from datetime import datetime, timedelta

        days = int(data.split(":")[1])
        today = datetime.now()
        end_date = today + timedelta(days=days)

        start_date_str = today.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        # Update user's date range
        with get_session() as session:
            user_repo = UserRepository(session)
            user_repo.set_date_range(user_id, start_date_str, end_date_str)

        # Track date range change
        await track_event(
            "date_range_set",
            user_id=user_id,
            range_days=days,
            range_direction="set"
        )

        await query.answer(f"✅ Date range set: next {days} days", show_alert=True)
        await show_status_inline(query, user_id)
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
            # Get user's date range for the success message
            start_date, end_date = get_user_date_range(user_id)
            service_info = get_service_info(service_id)
            office_name = get_office_name(office_id)

            # Track subscription added
            await track_event(
                "subscription_added",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"] if service_info else f"Service {service_id}",
                office_id=office_id
            )

            # Build success message with date range
            success_msg = (
                f"🎉 <b>Subscription Successful!</b>\n\n"
                f"<b>{service_info['name']}</b>\n"
                f"📍 Office: {office_name}\n\n"
                f"📅 You will receive notifications when appointments become available "
                f"between <b>{start_date}</b> and <b>{end_date}</b>.\n\n"
                f"💡 Tip: Use /setdates to change your date range anytime!"
            )

            # Show the detailed success message
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📊 My Subscriptions", callback_data="myservices"
                    )
                ],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                success_msg, reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            await query.answer("❌ Subscription failed", show_alert=True)

    elif data.startswith("unsub:"):
        # Remove subscription
        service_id = int(data[6:])

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            # Get subscription info before removal for analytics
            user_subs = sub_repo.get_user_subscriptions(user_id)
            sub_to_remove = next((s for s in user_subs if s["service_id"] == service_id), None)

            sub_repo.remove_subscription(user_id, service_id)

        # Track subscription removed
        if sub_to_remove:
            service_info = get_service_info(service_id)
            await track_event(
                "subscription_removed",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"] if service_info else f"Service {service_id}",
                office_id=sub_to_remove.get("office_id", 0),
                reason="user_initiated"
            )

        await query.answer("🗑 Unsubscribed", show_alert=True)
        await show_service_details(query, service_id, user_id)

    elif data == "unsub_all":
        # Confirm unsubscribe all
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Yes, Remove All", callback_data="unsub_all_confirm"
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="myservices"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ <b>Unsubscribe from All Services?</b>\n\n"
            "This will remove ALL your subscriptions. You can always subscribe again later.\n\n"
            "Are you sure?",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    elif data == "unsub_all_confirm":
        # Remove all subscriptions
        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            # Get subscriptions before deletion for analytics
            user_subs = sub_repo.get_user_subscriptions(user_id)
            count = sub_repo.delete_all_user_subscriptions(user_id)

        # Track each removed subscription
        for sub in user_subs:
            service_info = get_service_info(sub["service_id"])
            await track_event(
                "subscription_removed",
                user_id=user_id,
                service_id=sub["service_id"],
                service_name=service_info["name"] if service_info else f"Service {sub['service_id']}",
                office_id=sub.get("office_id", 0),
                reason="user_initiated"
            )

        await query.answer(f"🗑 Removed {count} subscription(s)", show_alert=True)
        await show_myservices(query, user_id)
