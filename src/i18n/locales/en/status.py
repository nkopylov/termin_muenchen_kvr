# ABOUTME: English texts for the /status command.
# ABOUTME: Keys are "status.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "status.not_registered": "❌ You are not registered.\n\nUse /start to register.",
    "status.seconds_ago": "{count} seconds ago",
    "status.minutes_ago": "{count} minutes ago",
    "status.hours_ago": "{count} hours ago",
    "status.next_in_seconds": "~{count} seconds",
    "status.next_in_minutes": "~{count} minutes",
    "status.last_check_never": "Never",
    "status.next_check_soon": "Soon",
    "status.found_today": "today",
    "status.found_yesterday": "yesterday",
    "status.found_days_ago": "{count} days ago",
    "status.found_recently": "recently",
    "status.appointments_found": "\n🎯 Appointments found: {found} (last: {latest})",
    "status.appointments_found_none": "\n🎯 Appointments found: 0",
    "status.interval_seconds": "{count} seconds",
    "status.message": (
        "📊 <b>Your Status</b>\n\n"
        "👤 User ID: <code>{user_id}</code>\n"
        "📋 Subscriptions: <b>{num_subs}</b>\n"
        "📅 Date Range: {start_date} to {end_date}\n"
        "🌐 Language: {language}\n\n"
        "🔍 Last checked: {last_check}\n"
        "⏱ Next check in: {next_check}\n"
        "⚙️ Check interval: {check_interval}"
        "{stats_line}"
    ),
}
