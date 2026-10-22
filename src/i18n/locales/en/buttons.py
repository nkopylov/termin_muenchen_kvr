# ABOUTME: English texts for inline button screens in handlers/buttons.py.
# ABOUTME: Keys are "buttons.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "buttons.menu_text": "🏠 <b>Main Menu</b>\n\nChoose an action:",
    "buttons.btn_subscribe_termins": "📋 Subscribe to available Termins",
    "buttons.btn_my_subscriptions": "📊 My Subscriptions",
    "buttons.btn_set_dates": "📅 Set Date Range",
    "buttons.btn_status": "ℹ️ Subscription Status",
    "buttons.not_registered": "❌ You are not registered.\n\nUse /start to register.",
    "buttons.seconds_ago": {
        "one": "{count} seconds ago",
        "other": "{count} seconds ago",
    },
    "buttons.minutes_ago": {
        "one": "{count} minutes ago",
        "other": "{count} minutes ago",
    },
    "buttons.hours_ago": {
        "one": "{count} hours ago",
        "other": "{count} hours ago",
    },
    "buttons.next_check_seconds": {
        "one": "~{count} seconds",
        "other": "~{count} seconds",
    },
    "buttons.next_check_minutes": {
        "one": "~{count} minutes",
        "other": "~{count} minutes",
    },
    "buttons.never": "Never",
    "buttons.soon": "Soon",
    "buttons.today": "today",
    "buttons.yesterday": "yesterday",
    "buttons.days_ago": {
        "one": "{count} days ago",
        "other": "{count} days ago",
    },
    "buttons.recently": "recently",
    "buttons.status_found": "\n🎯 Appointments found: {found} (last: {latest})",
    "buttons.status_found_none": "\n🎯 Appointments found: 0",
    "buttons.status": (
        "📊 <b>Your Status</b>\n\n"
        "👤 User ID: <code>{user_id}</code>\n"
        "📋 Subscriptions: <b>{num_subs}</b>\n"
        "📅 Date Range: {start_date} to {end_date}\n"
        "🌐 Language: {language}\n\n"
        "🔍 Last checked: {last_check}\n"
        "⏱ Next check in: {next_check}\n"
        "⚙️ Check interval: {check_interval} seconds"
        "{stats_line}\n\n"
        "👥 Total Users: <b>{total_users}</b>"
    ),
    "buttons.setdates": (
        "📅 <b>Set Date Range</b>\n\n"
        "Current range: <b>{start_date}</b> to <b>{end_date}</b>\n\n"
        "Choose a preset or use a custom range:\n\n"
        "<b>Custom Range:</b>\n"
        "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
        "<b>Example:</b> <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "buttons.preset_2_days": "📅 Next 2 days ({today} to {end_date})",
    "buttons.preset_week": "📅 Next week ({today} to {end_date})",
    "buttons.preset_30_days": "📅 Next 30 days ({today} to {end_date})",
    "buttons.preset_3_months": "📅 Next 3 months ({today} to {end_date})",
    "buttons.preset_6_months": "📅 Next 6 months ({today} to {end_date})",
    "buttons.date_range_set": {
        "one": "✅ Date range set: next {count} days",
        "other": "✅ Date range set: next {count} days",
    },
    "buttons.no_services_in_category": "❌ No services found in {category} category.",
    "buttons.btn_previous": "◀️ Previous",
    "buttons.btn_next": "Next ▶️",
    "buttons.pagination": "Showing {first}-{last} of {total} services",
    "buttons.service_not_found": "❌ Service not found.",
    "buttons.service_details": "<b>{name}</b>\n\nService ID: <code>{service_id}</code>\n",
    "buttons.max_quantity": "Max. Quantity: {max_quantity}\n",
    "buttons.service_status": "\nStatus: {status}",
    "buttons.subscribed": "✅ Subscribed",
    "buttons.not_subscribed": "⭕ Not subscribed",
    "buttons.btn_unsubscribe": "🗑 Unsubscribe",
    "buttons.btn_subscribe": "✅ Subscribe",
    "buttons.btn_back": "◀️ Back",
    "buttons.btn_categories": "🏠 Categories",
    "buttons.no_offices": "❌ No offices found for '{service}'.",
    "buttons.select_office": (
        "<b>{service}</b>\n\n📍 Please select an office:\n({available} available)"
    ),
    "buttons.office_fallback": "Office {office_id}",
    "buttons.offices_truncated": "\n\n⚠️ Only the first 20 of {total} offices are shown.",
    "buttons.no_subscriptions": (
        "📋 <b>No Subscriptions</b>\n\n"
        "You haven't subscribed to any services yet.\n"
        "Use /subscribe to start monitoring appointment availability!"
    ),
    "buttons.subscriptions_header": (
        "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"
    ),
    "buttons.unknown_office": "Unknown Office",
    "buttons.subscription_item": (
        "• <b>{service}</b>\n   📍 {office}\n   📅 Subscribed: {subscribed_at}\n\n"
    ),
    "buttons.subscriptions_total": {
        "one": "<b>Total:</b> {count} subscription(s)",
        "other": "<b>Total:</b> {count} subscription(s)",
    },
    "buttons.btn_unsubscribe_all": "🗑 Unsubscribe from All",
    "buttons.booking_interrupted": (
        "❌ Your booking session was interrupted (bot restarted).\n\n"
        "Please start a new booking from an appointment notification."
    ),
    "buttons.select_category": "📋 <b>Select a Category:</b>",
    "buttons.subscription_success": (
        "🎉 <b>Subscription Successful!</b>\n\n"
        "<b>{service}</b>\n"
        "📍 Office: {office}\n\n"
        "📅 You will receive notifications when appointments become available "
        "between <b>{start_date}</b> and <b>{end_date}</b>.\n\n"
        "💡 Tip: Use /setdates to change your date range anytime!"
    ),
    "buttons.subscription_failed": "❌ Subscription failed",
    "buttons.unsubscribed": "🗑 Unsubscribed",
    "buttons.unsub_all_confirm": (
        "⚠️ <b>Unsubscribe from All Services?</b>\n\n"
        "This will remove ALL your subscriptions. You can always subscribe again later.\n\n"
        "Are you sure?"
    ),
    "buttons.btn_yes_remove_all": "✅ Yes, Remove All",
    "buttons.btn_cancel": "❌ Cancel",
    "buttons.removed_subscriptions": {
        "one": "🗑 Removed {count} subscription(s)",
        "other": "🗑 Removed {count} subscription(s)",
    },
}
