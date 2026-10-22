# ABOUTME: English texts for the Settings screen and its buttons.
# ABOUTME: Keys are "settings.<name>"; {contact} is already HTML-escaped by the caller.

MESSAGES: dict[str, str | dict[str, str]] = {
    "settings.text": (
        "⚙️ <b>Settings</b>\n\n🌐 Language: {language}\n📇 Booking details: {contact}"
    ),
    "settings.contact_none": "not saved yet",
    "settings.btn_forget": "🧹 Forget booking details",
    "settings.btn_delete": "🗑 Delete my data",
    "settings.forgotten": "Booking details forgotten.",
}
