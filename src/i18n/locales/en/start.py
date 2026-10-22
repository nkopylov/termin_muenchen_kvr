# ABOUTME: English texts for the /start command.
# ABOUTME: Keys are "start.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "start.welcome": (
        "👋 <b>Welcome to Munich Appointment Bot!</b>\n\n"
        "🎯 <b>What I do:</b>\n"
        "I monitor the Munich city appointment system (Ausländerbehörde, "
        "Bürgeramt, KVR) 24/7 and notify you instantly when appointments become available.\n\n"
        "🚀 <b>How it works:</b>\n"
        "1️⃣ <b>Subscribe</b> to services you need (e.g., visa, passport, residence permit)\n"
        "2️⃣ <b>Set your date range</b> - when you're available for appointments\n"
        "3️⃣ <b>Get notified</b> immediately when slots open up\n"
        "4️⃣ <b>Book instantly</b> through the bot or on the website\n\n"
        "⚡ <b>Getting Started:</b>\n"
        "• Set your date range: /setdates\n"
        "• Subscribe to services: /subscribe\n"
        "• View main menu: /menu\n"
        "• Get help: /help\n\n"
        "💡 <b>Tip:</b> Set a realistic date range (e.g., next 3 months) for better results!"
    ),
}
