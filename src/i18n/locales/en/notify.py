# ABOUTME: English texts for appointment notifications.
# ABOUTME: Keys are "notify.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "notify.initial": (
        "🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉\n\n"
        "<b>{service_name}</b>\n\n"
        "Available appointments:\n{dates}\n\n"
        "🔗 <a href='{booking_url}'>Book appointment now!</a>\n\n"
        "⏳ Loading time slots..."
    ),
    "notify.final": (
        "🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉\n\n"
        "<b>{service_name}</b>\n\n"
        "Available appointments:\n{dates}\n\n"
        "🔗 <a href='{booking_url}'>Book appointment now!</a>\n\n"
        "⚡ Act fast - Appointments fill up quickly!"
    ),
    "notify.more_days": {
        "one": "... and {count} more day",
        "other": "... and {count} more days",
    },
    "notify.unknown_date": "Unknown date",
    "notify.btn_book_date": "📅 Book: {date}",
    "notify.btn_book_manually": "🔗 Book manually on website",
}
