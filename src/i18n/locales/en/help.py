# ABOUTME: English texts for the /help command.
# ABOUTME: Keys are "help.<name>"; {find} is the reply keyboard's Find label.

MESSAGES: dict[str, str | dict[str, str]] = {
    "help.text": (
        "❓ <b>How it works</b>\n\n"
        "1. Tell me what you need: tap {find} or just type it, e.g. “passport”.\n"
        "2. Choose an office and when you need the appointment.\n"
        "3. I check the city's calendar around the clock and message you "
        "as soon as a slot is free.\n"
        "4. Book right here in the chat or on the city website.\n\n"
        "<b>Commands</b>\n"
        "/find - find a Termin\n"
        "/watches - my watches\n"
        "/settings - language, saved booking details, deleting data\n"
        "/language - change language\n"
        "/stop - delete my data\n"
        "/help - this help\n\n"
        "Found a bug? https://github.com/nkopylov/termin_muenchen_kvr"
    ),
}
