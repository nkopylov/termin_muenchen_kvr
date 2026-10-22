# ABOUTME: English texts for /start: the welcome, the returning-user greeting and the menu announcement.
# ABOUTME: Keys are "start.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "start.welcome": (
        "👋 <b>Hi! I find free Termins at Munich city offices.</b>\n"
        "Tell me what you need, and I'll message you as soon as a slot opens up. "
        "The menu is at the bottom of the chat."
    ),
    "start.welcome_back": (
        "👋 <b>Welcome back!</b>\nThe menu is at the bottom of the chat."
    ),
    "start.not_registered": "👋 Welcome! Please use /start to register first.",
    "start.announce": (
        "🆕 <b>The bot has a new menu</b>\n"
        "Your subscriptions are now <b>watches</b>: open {watches} to see them, "
        "change the time or pause them. The menu is at the bottom of the chat."
    ),
}
