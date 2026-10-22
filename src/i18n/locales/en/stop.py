# ABOUTME: English texts for deleting all of a user's data (/stop and Settings).
# ABOUTME: Keys are "stop.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "stop.confirm": (
        "🗑 <b>Delete all your data?</b>\n\n"
        "I will stop all your watches and forget your language and saved booking "
        "details. This cannot be undone."
    ),
    "stop.btn_yes": "🗑 Yes, delete",
    "stop.btn_no": "↩️ No, keep",
    "stop.kept": "👍 Nothing was deleted.",
    "stop.done": (
        "👋 Done. I deleted all your data and stopped all your watches.\n"
        "Send /start whenever you want to use me again."
    ),
}
