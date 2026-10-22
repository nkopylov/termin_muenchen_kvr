# ABOUTME: English texts for the /setdates command.
# ABOUTME: Keys are "setdates.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "setdates.btn_next_2_days": "📅 Next 2 days ({start} to {end})",
    "setdates.btn_next_week": "📅 Next week ({start} to {end})",
    "setdates.btn_next_30_days": "📅 Next 30 days ({start} to {end})",
    "setdates.btn_next_3_months": "📅 Next 3 months ({start} to {end})",
    "setdates.btn_next_6_months": "📅 Next 6 months ({start} to {end})",
    "setdates.presets": (
        "📅 <b>Set Date Range</b>\n\n"
        "Choose a preset date range or use a custom range:\n\n"
        "<b>Custom Range:</b>\n"
        "<code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
        "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.invalid_format": (
        "❌ Invalid format.\n\n"
        "Usage: <code>/setdates YYYY-MM-DD YYYY-MM-DD</code>\n\n"
        "Example:\n"
        "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
        "Or use /setdates without arguments for quick presets."
    ),
    "setdates.invalid_range": (
        "❌ Invalid date range. End date must be after start date.\n\n"
        "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.invalid_date": (
        "❌ Invalid date format. Please use YYYY-MM-DD\n\n"
        "Example: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.updated": (
        "✅ Date range updated!\n\n"
        "From: <b>{start_date}</b>\n"
        "To: <b>{end_date}</b>\n\n"
        "The bot will now search for appointments in this date range."
    ),
}
