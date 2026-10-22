# ABOUTME: English texts of watch alert messages in every lifecycle state and their buttons.
# ABOUTME: Keys are "alert.<name>"; {summary} is already HTML-escaped by the renderer.

MESSAGES: dict[str, str | dict[str, str]] = {
    "alert.slots": "🎉 <b>Free slots</b>\n{summary}\n\n📅 {day}: {times}{more}",
    "alert.also_free": "Also free: {days}",
    "alert.also_free_more": {
        "one": "Also free: {days} and {count} more day",
        "other": "Also free: {days} and {count} more days",
    },
    "alert.times_unknown": "times on the website",
    "alert.updated_existing": "✏️ I updated your existing watch for this service.",
    "alert.none_yet": (
        "🔎 <b>Watching</b>\n{summary}\n\n"
        "No free slots yet. I'll message you as soon as one appears."
    ),
    "alert.check_failed": (
        "🔎 <b>Watching</b>\n{summary}\n\n"
        "I couldn't check right now. I'll keep trying and message you when slots appear."
    ),
    "alert.empty_now": (
        "🔎 <b>Watching</b>\n{summary}\n\n"
        "😕 No free slots right now (as of {time}). I'm still watching."
    ),
    "alert.outdated": "⌛ Outdated — this watch continues in a newer message.",
    "alert.final_booked": "✅ <b>Booked</b>\n{summary}\n\nThis watch is finished.",
    "alert.final_stopped": "⏹ <b>Stopped watching</b>\n{summary}",
    "alert.final_paused": "⏸ <b>Paused</b>\n{summary}\n\nYou can resume it in My watches.",
    "alert.final_deadline": "⌛ <b>Watch ended</b>: the date has passed.\n{summary}",
    "alert.final_gone": (
        "⚠️ <b>Watch ended</b>: this office no longer takes online bookings "
        "for this service.\n{summary}"
    ),
    "alert.deadline": (
        "⌛ <b>Your watch has ended</b>\n{summary}\n\n"
        "The date has passed. Extend the watch or start a new search."
    ),
    "alert.gone": (
        "⚠️ <b>Your watch has ended</b>\n{summary}\n\n"
        "This office no longer takes online bookings for this service."
    ),
    "alert.btn_book": "📅 Book {day}",
    "alert.btn_website": "🌐 Website",
    "alert.btn_stop": "⏹ Stop watching",
    "alert.btn_extend": "🔁 Extend",
    "alert.btn_new_search": "🔎 New search",
    "alert.btn_any_office": "🏢 Any office",
    "alert.booking_timed_out": (
        "⌛ The booking session expired. I'll send you the current free slots."
    ),
}
