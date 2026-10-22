# ABOUTME: English descriptions for the bot command list shown by Telegram.
# ABOUTME: Keys are "commands.<command name>"; Telegram allows 1-256 characters.

MESSAGES: dict[str, str | dict[str, str]] = {
    "commands.start": "Start the bot and register",
    "commands.menu": "Show main menu",
    "commands.subscribe": "Subscribe to available Termins",
    "commands.myservices": "View your subscriptions",
    "commands.setdates": "Set date range filter",
    "commands.status": "Show your status",
    "commands.find": "Find a Termin",
    "commands.watches": "My watches",
    "commands.settings": "Settings",
    "commands.help": "Show help and documentation",
    "commands.language": "Change language",
    "commands.stop": "Unsubscribe and delete data",
}
