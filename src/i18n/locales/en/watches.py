# ABOUTME: English texts for the My watches screen and its buttons.
# ABOUTME: Keys are "watches.<name>"; {summary} is already HTML-escaped by the caller.

MESSAGES: dict[str, str | dict[str, str]] = {
    "watches.header": "👀 <b>My watches</b> ({count} of {limit})",
    "watches.header_over": "👀 <b>My watches</b> ({count})",
    "watches.line": "<b>{n}.</b> {summary}\n      {state}{checked}",
    "watches.checked": " · checked {ago}",
    "watches.empty": (
        "👀 <b>My watches</b>\n\n"
        "You're not watching anything. Tell me what you need, "
        "and I'll look for a free Termin."
    ),
    "watches.btn_time": "{n}. 🕒 Time",
    "watches.btn_pause": "⏸ Pause",
    "watches.btn_resume": "▶️ Resume",
    "watches.btn_stop": "⏹ Stop",
    "watches.btn_again": "{n}. 🔁 Search again",
    "watches.btn_any_office": "{n}. 🏢 Any office",
    "watches.btn_new": "➕ New watch",
    "watches.btn_find": "🔎 Find a Termin",
    "watches.stop_confirm": (
        "⏹ <b>Stop this watch?</b>\n{summary}\n\n"
        "I'll stop looking for free slots for it."
    ),
    "watches.btn_stop_yes": "⏹ Yes, stop",
    "watches.btn_stop_no": "↩️ No, keep watching",
    "watches.not_open": "This watch has already ended.",
}
