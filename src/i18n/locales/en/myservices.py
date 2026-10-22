# ABOUTME: English texts for the /myservices command.
# ABOUTME: Keys are "myservices.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "myservices.empty": (
        "📋 <b>No Subscriptions</b>\n\nYou haven't subscribed to any services yet.\n"
        "Use /subscribe to start monitoring appointment availability!"
    ),
    "myservices.header": (
        "📋 <b>Your Subscriptions</b>\n\nYou are monitoring these services:\n\n"
    ),
    "myservices.item": (
        "• <b>{service}</b>\n   📍 {office}\n   📅 Subscribed: {date}\n\n"
    ),
    "myservices.unknown_office": "Unknown Office",
    "myservices.total": "<b>Total:</b> {count} subscription(s)",
    "myservices.btn_subscribe_more": "📋 Subscribe to More",
    "myservices.btn_unsubscribe_all": "🗑 Unsubscribe from All",
}
