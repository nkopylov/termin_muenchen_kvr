# ABOUTME: English texts for the Find flow: popular services, search, browse, office and time steps.
# ABOUTME: Keys are "find.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "find.title": (
        "🔎 <b>What do you need?</b>\n"
        "Pick a service below or just type what you're looking for, "
        "e.g. <i>passport</i> or <i>Anmeldung</i>."
    ),
    "find.btn_all": "📚 All services",
    "find.results": "🔎 Services matching <b>{query}</b>:",
    "find.nothing": (
        "😕 I found nothing for <b>{query}</b>.\n"
        "Try another word (English, German or Russian) or browse all services."
    ),
    "find.categories": "📚 <b>All services</b>\nChoose a category:",
    "find.category_page": "<b>{category}</b>\nServices {first}–{last} of {total}:",
    "find.btn_prev": "⬅️ Previous",
    "find.btn_next": "Next ➡️",
    "find.btn_back": "↩️ Back",
    "find.unavailable": (
        "😕 This service can't be booked online right now. Please choose another one."
    ),
    "find.where": "🏢 <b>{service}</b>\nWhich office suits you?",
    "find.btn_any_office": "🏢 Any office",
    "find.when": "🗓 <b>{service}</b> · {where}\nWhen do you need the appointment?",
    "find.when_edit": (
        "🗓 <b>Change the time</b>\n{summary}\n\nWhen do you need the appointment?"
    ),
    "find.when_again": (
        "🔁 <b>Search again</b>\n{summary}\n\nWhen do you need the appointment?"
    ),
    "find.when_existing": (
        "ℹ️ You already have a watch for this service. Your choice will update it."
    ),
    "find.btn_asap": "⚡ As soon as possible",
    "find.btn_2w": "Within 2 weeks",
    "find.btn_1m": "Within 1 month",
    "find.btn_3m": "Within 3 months",
    "find.btn_before": "📅 Before a date…",
    "find.btn_between": "📆 Between two dates…",
    "find.ask_before": (
        "📅 Type the date by which you need the appointment, e.g. <code>15.11</code>, "
        "<code>15.11.2026</code> or <code>2026-11-15</code>.\n"
        "I'll look for free slots before that day."
    ),
    "find.ask_range": (
        "📆 Type two dates: the first and the last day that suit you, "
        "e.g. <code>15.11 - 30.11</code> or <code>2026-11-15 2026-11-30</code>."
    ),
    "find.btn_cancel": "✖️ Cancel",
    "find.date_format": (
        "🤔 I couldn't understand the date. Please write it like <code>15.11</code>, "
        "<code>15.11.2026</code> or <code>2026-11-15</code>; for a period, two such dates."
    ),
    "find.date_past": "⏳ That date has already passed. Please type a later one.",
    "find.date_too_far": (
        "🔭 That's too far ahead: I can search up to {max_date}. "
        "Please type an earlier date."
    ),
    "find.date_order": (
        "🔀 The first date is after the second one. Please type the earlier date first."
    ),
    "find.limit": {
        "one": (
            "✋ You already have {count} watch, the maximum. "
            "Stop it in My watches to start a new one."
        ),
        "other": (
            "✋ You already have {count} watches, the maximum. "
            "Stop one of them in My watches to start a new one."
        ),
    },
    "find.limit_over": (
        "✋ You have {open} watches, but the maximum is {limit}. "
        "Stop {count} of them in My watches to start a new one."
    ),
    "find.checking": "🔎 Checking <b>{service}</b>…",
}
