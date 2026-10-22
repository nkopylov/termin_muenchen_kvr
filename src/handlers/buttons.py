"""
Button callback handlers for Telegram inline keyboards.
Handles all button interactions including menus, service subscription, and navigation.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.config import get_config
from src.database import get_session
from src.i18n import t
from src.i18n.user_language import get_user_language
from src.repositories import SubscriptionRepository, UserRepository
from src.services.analytics_service import track_event
from src.services.appointment_checker import get_stats, get_user_date_range
from src.services_manager import (
    CATEGORY_KEYWORDS,
    categorize_services,
    get_category_for_service,
    get_office_name,
    get_service_info,
)


def main_menu_button(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        t("common.btn_main_menu", lang), callback_data="main_menu"
    )


async def show_main_menu(query, user_id: int, lang: str | None = None):
    """Show main menu as inline message"""
    lang = lang or get_user_language(user_id)
    menu_text = t("buttons.menu_text", lang)

    keyboard = [
        [
            InlineKeyboardButton(
                t("buttons.btn_subscribe_termins", lang), callback_data="categories"
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.btn_my_subscriptions", lang), callback_data="myservices"
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.btn_set_dates", lang), callback_data="setdates"
            )
        ],
        [InlineKeyboardButton(t("buttons.btn_status", lang), callback_data="status")],
        [
            InlineKeyboardButton(
                t("language.btn_menu", lang),
                callback_data="language",
            )
        ],
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


async def show_status_inline(query, user_id: int, lang: str | None = None):
    """Show user's status inline"""
    from datetime import datetime

    from src.repositories import AppointmentLogRepository

    lang = lang or get_user_language(user_id)

    with get_session() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        log_repo = AppointmentLogRepository(session)

        user = user_repo.get_user(user_id)
        if not user:
            keyboard = [[main_menu_button(lang)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                t("buttons.not_registered", lang),
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return

        subs = sub_repo.get_user_subscriptions(user_id)
        total_users = len(user_repo.get_all_users())
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
            last_check_str = t("buttons.seconds_ago", lang, count=int(time_since_check))
        elif time_since_check < 3600:
            last_check_str = t(
                "buttons.minutes_ago", lang, count=int(time_since_check / 60)
            )
        else:
            last_check_str = t(
                "buttons.hours_ago", lang, count=int(time_since_check / 3600)
            )

        # Calculate next check estimate
        next_check_seconds = max(0, check_interval - time_since_check)
        if next_check_seconds < 60:
            next_check_str = t(
                "buttons.next_check_seconds", lang, count=int(next_check_seconds)
            )
        else:
            next_check_str = t(
                "buttons.next_check_minutes", lang, count=int(next_check_seconds / 60)
            )
    else:
        last_check_str = t("buttons.never", lang)
        next_check_str = t("buttons.soon", lang)

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
                    latest_str = t("buttons.today", lang)
                elif days_ago == 1:
                    latest_str = t("buttons.yesterday", lang)
                else:
                    latest_str = t("buttons.days_ago", lang, count=days_ago)
            except (ValueError, TypeError):
                latest_str = t("buttons.recently", lang)
        else:
            latest_str = t("buttons.recently", lang)
        stats_line = t(
            "buttons.status_found",
            lang,
            found=user_appointments_count,
            latest=latest_str,
        )
    else:
        stats_line = t("buttons.status_found_none", lang)

    message = t(
        "buttons.status",
        lang,
        user_id=user_id,
        num_subs=num_subs,
        start_date=start_date,
        end_date=end_date,
        language=t(f"language.btn_{lang}", lang),
        last_check=last_check_str,
        next_check=next_check_str,
        check_interval=t("status.interval_seconds", lang, count=check_interval),
        stats_line=stats_line,
        total_users=total_users,
    )

    keyboard = [[main_menu_button(lang)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_setdates_inline(query, user_id: int, lang: str | None = None):
    """Show instructions for setting date range"""
    from datetime import datetime, timedelta

    lang = lang or get_user_language(user_id)
    start_date, end_date = get_user_date_range(user_id)

    # Calculate preset dates
    today = datetime.now()
    date_2 = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    date_7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    date_30 = (today + timedelta(days=30)).strftime("%Y-%m-%d")
    date_90 = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    date_180 = (today + timedelta(days=180)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    message = t("buttons.setdates", lang, start_date=start_date, end_date=end_date)

    keyboard = [
        [
            InlineKeyboardButton(
                t("buttons.preset_2_days", lang, today=today_str, end_date=date_2),
                callback_data="setdates:2",
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.preset_week", lang, today=today_str, end_date=date_7),
                callback_data="setdates:7",
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.preset_30_days", lang, today=today_str, end_date=date_30),
                callback_data="setdates:30",
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.preset_3_months", lang, today=today_str, end_date=date_90),
                callback_data="setdates:90",
            )
        ],
        [
            InlineKeyboardButton(
                t("buttons.preset_6_months", lang, today=today_str, end_date=date_180),
                callback_data="setdates:180",
            )
        ],
        [main_menu_button(lang)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_categories(query, lang: str):
    """Show all service categories"""
    categories = categorize_services()
    keyboard = []
    cat_items = list(categories.items())

    for i in range(0, len(cat_items), 2):
        row = []
        for j in range(2):
            if i + j < len(cat_items):
                category_id, services = cat_items[i + j]
                row.append(
                    InlineKeyboardButton(
                        f"{t(f'categories.{category_id}', lang)} ({len(services)})",
                        callback_data=f"cat:{category_id}",
                    )
                )
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        t("buttons.select_category", lang), reply_markup=reply_markup, parse_mode="HTML"
    )


async def show_category_services(query, category_id: str, page: int, lang: str):
    """Show services in a category"""
    # Buttons in stale messages may carry a category label instead of an id
    if category_id not in CATEGORY_KEYWORDS:
        await show_categories(query, lang)
        return

    category_label = t(f"categories.{category_id}", lang)
    categories = categorize_services()
    services = categories.get(category_id, [])

    if not services:
        await query.edit_message_text(
            t("buttons.no_services_in_category", lang, category=category_label)
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
                t("buttons.btn_previous", lang),
                callback_data=f"catpage:{category_id}:{page - 1}",
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            t("common.btn_menu_short", lang), callback_data="main_menu"
        )
    )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                t("buttons.btn_next", lang),
                callback_data=f"catpage:{category_id}:{page + 1}",
            )
        )
    keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    pagination_text = t(
        "buttons.pagination",
        lang,
        first=start_idx + 1,
        last=end_idx,
        total=len(services),
    )

    try:
        await query.edit_message_text(
            f"<b>{category_label}</b>\n\n{pagination_text}",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        # Ignore "message is not modified" errors
        if "message is not modified" not in str(e).lower():
            raise


async def show_service_details(
    query, service_id: int, user_id: int, lang: str | None = None
):
    """Show service details and subscribe button"""
    lang = lang or get_user_language(user_id)
    service_info = get_service_info(service_id)

    if not service_info:
        await query.edit_message_text(t("buttons.service_not_found", lang))
        return

    # Check if already subscribed
    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        user_subs = sub_repo.get_user_subscriptions(user_id)

    is_subscribed = any(sub["service_id"] == service_id for sub in user_subs)

    # Build message
    message = t(
        "buttons.service_details",
        lang,
        name=service_info["name"],
        service_id=service_info["id"],
    )

    if service_info.get("maxQuantity"):
        message += t(
            "buttons.max_quantity", lang, max_quantity=service_info["maxQuantity"]
        )

    status = t(
        "buttons.subscribed" if is_subscribed else "buttons.not_subscribed", lang
    )
    message += t("buttons.service_status", lang, status=status)

    # Build keyboard
    keyboard = []
    if is_subscribed:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("buttons.btn_unsubscribe", lang),
                    callback_data=f"unsub:{service_id}",
                )
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("buttons.btn_subscribe", lang),
                    callback_data=f"addsub:{service_id}",
                )
            ]
        )

    # Back button
    category = get_category_for_service(service_id)
    if category:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("buttons.btn_back", lang), callback_data=f"cat:{category}"
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                t("buttons.btn_categories", lang), callback_data="categories"
            )
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_office_selection(
    query, service_id: int, user_id: int, lang: str | None = None
):
    """Show office selection for a service subscription"""
    from src.services_manager import get_offices_for_service

    lang = lang or get_user_language(user_id)
    service_info = get_service_info(service_id)
    if not service_info:
        await query.edit_message_text(t("buttons.service_not_found", lang))
        return

    # Get all offices that support this service
    offices = get_offices_for_service(service_id)

    back_button = InlineKeyboardButton(
        t("buttons.btn_back", lang), callback_data=f"srv:{service_id}"
    )

    if not offices:
        await query.edit_message_text(
            t("buttons.no_offices", lang, service=service_info["name"]),
            reply_markup=InlineKeyboardMarkup([[back_button]]),
        )
        return

    # Build message
    message = t(
        "buttons.select_office",
        lang,
        service=service_info["name"],
        available=len(offices),
    )

    # Build keyboard with office options (max 10 per page for now)
    keyboard = []
    for office in offices[:20]:  # Show first 20 offices
        if "name" in office:
            office_name = office["name"]
        else:
            office_name = t("buttons.office_fallback", lang, office_id=office["id"])
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
        message += t("buttons.offices_truncated", lang, total=len(offices))

    # Back button
    keyboard.append([back_button])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def show_myservices(query, user_id: int, lang: str | None = None):
    """Show user's subscriptions inline"""
    lang = lang or get_user_language(user_id)

    with get_session() as session:
        sub_repo = SubscriptionRepository(session)
        subscriptions = sub_repo.get_user_subscriptions(user_id)

    if not subscriptions:
        keyboard = [[main_menu_button(lang)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            t("buttons.no_subscriptions", lang),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    message = t("buttons.subscriptions_header", lang)

    for sub in subscriptions:
        service_info = get_service_info(sub["service_id"])
        if service_info:
            # Add office information
            office_id = sub.get("office_id")
            office_name = (
                get_office_name(office_id, lang)
                if office_id
                else t("buttons.unknown_office", lang)
            )
            message += t(
                "buttons.subscription_item",
                lang,
                service=service_info["name"],
                office=office_name,
                subscribed_at=sub["subscribed_at"][:10],
            )

    message += t("buttons.subscriptions_total", lang, count=len(subscriptions))

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
            [
                InlineKeyboardButton(
                    t("buttons.btn_unsubscribe_all", lang), callback_data="unsub_all"
                )
            ]
        )
    keyboard.append([main_menu_button(lang)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data
    lang = get_user_language(user_id, context)

    # Check for orphaned booking sessions (bot restarted during booking)
    from src.services.queue_manager import is_user_in_queue

    if is_user_in_queue(user_id) and (
        data.startswith("time_") or data == "cancel_booking"
    ):
        # User has an active booking session but ConversationHandler doesn't know about it
        from src.commands.booking import delete_booking_session

        delete_booking_session(user_id)
        await query.edit_message_text(t("buttons.booking_interrupted", lang))
        return

    # Handle main menu
    if data == "main_menu":
        await show_main_menu(query, user_id, lang)
        return

    # Handle menu actions
    if data == "show_stats":
        await show_stats_inline(query)
        return

    if data == "myservices":
        await show_myservices(query, user_id, lang)
        return

    if data == "status":
        await show_status_inline(query, user_id, lang)
        return

    if data == "setdates":
        await show_setdates_inline(query, user_id, lang)
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
            "date_range_set", user_id=user_id, range_days=days, range_direction="set"
        )

        await query.answer(
            t("buttons.date_range_set", lang, count=days), show_alert=True
        )
        await show_status_inline(query, user_id, lang)
        return

    if data == "categories":
        # Show all categories
        await show_categories(query, lang)

    elif data.startswith("cat:"):
        # Show services in category
        category = data[4:]
        await show_category_services(query, category, 0, lang)

    elif data.startswith("catpage:"):
        # Paginated category view
        parts = data.split(":")
        category = parts[1]
        page = int(parts[2])
        await show_category_services(query, category, page, lang)

    elif data.startswith("srv:"):
        # Show service details
        service_id = int(data[4:])
        await show_service_details(query, service_id, user_id, lang)

    elif data.startswith("addsub:"):
        # Show office selection for subscription
        service_id = int(data[7:])
        await show_office_selection(query, service_id, user_id, lang)

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
            office_name = get_office_name(office_id, lang)

            # Track subscription added
            await track_event(
                "subscription_added",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"]
                if service_info
                else f"Service {service_id}",
                office_id=office_id,
            )

            # Build success message with date range
            success_msg = t(
                "buttons.subscription_success",
                lang,
                service=service_info["name"],
                office=office_name,
                start_date=start_date,
                end_date=end_date,
            )

            # Show the detailed success message
            keyboard = [
                [
                    InlineKeyboardButton(
                        t("buttons.btn_my_subscriptions", lang),
                        callback_data="myservices",
                    )
                ],
                [main_menu_button(lang)],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                success_msg, reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            await query.answer(t("buttons.subscription_failed", lang), show_alert=True)

    elif data.startswith("unsub:"):
        # Remove subscription
        service_id = int(data[6:])

        with get_session() as session:
            sub_repo = SubscriptionRepository(session)
            # Get subscription info before removal for analytics
            user_subs = sub_repo.get_user_subscriptions(user_id)
            sub_to_remove = next(
                (s for s in user_subs if s["service_id"] == service_id), None
            )

            sub_repo.remove_subscription(user_id, service_id)

        # Track subscription removed
        if sub_to_remove:
            service_info = get_service_info(service_id)
            await track_event(
                "subscription_removed",
                user_id=user_id,
                service_id=service_id,
                service_name=service_info["name"]
                if service_info
                else f"Service {service_id}",
                office_id=sub_to_remove.get("office_id", 0),
                reason="user_initiated",
            )

        await query.answer(t("buttons.unsubscribed", lang), show_alert=True)
        await show_service_details(query, service_id, user_id, lang)

    elif data == "unsub_all":
        # Confirm unsubscribe all
        keyboard = [
            [
                InlineKeyboardButton(
                    t("buttons.btn_yes_remove_all", lang),
                    callback_data="unsub_all_confirm",
                ),
                InlineKeyboardButton(
                    t("buttons.btn_cancel", lang), callback_data="myservices"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            t("buttons.unsub_all_confirm", lang),
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
                service_name=service_info["name"]
                if service_info
                else f"Service {sub['service_id']}",
                office_id=sub.get("office_id", 0),
                reason="user_initiated",
            )

        await query.answer(
            t("buttons.removed_subscriptions", lang, count=count), show_alert=True
        )
        await show_myservices(query, user_id, lang)
