# ABOUTME: English texts for the booking conversation.
# ABOUTME: Keys are "booking.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "booking.fetching_slots": (
        "📅 Selected date: {date}\n\nFetching available time slots..."
    ),
    "booking.select_time": (
        "📅 Available time slots for {date}:\n\nPlease select a time:"
    ),
    "booking.invalid_data": "❌ Invalid booking data. Please try again.",
    "booking.watch_ended": "This watch has ended. Start a new search with 🔎 Find a Termin.",
    "booking.day_gone": "😕 No free times left on {date}.",
    "booking.times_failed": "⚠️ I couldn't load the times for {date} right now.",
    "booking.will_send_days": "I'll keep watching and send you the updated free days.",
    "booking.use_saved": (
        "🕐 {time}\n📍 {office}\n\nBook with your saved details?\n👤 {name}\n📧 {email}"
    ),
    "booking.btn_yes_book": "✅ Yes, book it",
    "booking.btn_change": "✏️ Enter other details",
    "booking.btn_cancel": "❌ Cancel",
    "booking.btn_cancel_booking": "❌ Cancel Booking",
    "booking.btn_confirm": "✅ Confirm Booking",
    "booking.cancelled": "❌ Booking cancelled.",
    "booking.session_cleared": (
        "❌ Your booking session expired or was cleared.\n\n"
        "Please start a new booking from an appointment notification."
    ),
    "booking.time_on_date": "{time} on {date}",
    "booking.time_on_long_date": "{time} on {weekday}, {month} {day:02d}, {year}",
    "booking.weekday_0": "Monday",
    "booking.weekday_1": "Tuesday",
    "booking.weekday_2": "Wednesday",
    "booking.weekday_3": "Thursday",
    "booking.weekday_4": "Friday",
    "booking.weekday_5": "Saturday",
    "booking.weekday_6": "Sunday",
    "booking.month_1": "January",
    "booking.month_2": "February",
    "booking.month_3": "March",
    "booking.month_4": "April",
    "booking.month_5": "May",
    "booking.month_6": "June",
    "booking.month_7": "July",
    "booking.month_8": "August",
    "booking.month_9": "September",
    "booking.month_10": "October",
    "booking.month_11": "November",
    "booking.month_12": "December",
    "booking.ask_name": (
        "✅ Selected time: {time}\n\n"
        "Please enter your full name (as it appears on your documents):"
    ),
    "booking.name_not_full": (
        "❌ Please enter your full name (first and last name).\n\nExample: John Smith"
    ),
    "booking.name_too_short": "❌ Name is too short. Please enter your full name:",
    "booking.ask_email": (
        "✅ Name: {name}\n\n"
        "Please enter your email address (you'll receive a confirmation email):"
    ),
    "booking.email_invalid": (
        "❌ Invalid email address. Please enter a valid email:\n\n"
        "Example: your.name@example.com"
    ),
    "booking.confirm_summary": (
        "📋 <b>Please confirm your booking:</b>\n\n"
        "🕐 Time: {time}\n"
        "👤 Name: {name}\n"
        "📧 Email: {email}\n\n"
        "<b>Important:</b> You will receive a confirmation email. "
        "You MUST click the link in that email to finalize your appointment!"
    ),
    "booking.processing": "⏳ Processing your booking...\nThis may take a few seconds.",
    "booking.success": (
        "🎉 <b>Booking Successful!</b> 🎉\n\n"
        "📋 Booking ID: {process_id}\n"
        "🕐 Time: {time}\n"
        "👤 Name: {name}\n"
        "📧 Email: {email}\n\n"
        "<b>⚠️ IMPORTANT - Next Steps:</b>\n\n"
        "1. Check your email inbox at <b>{email}</b>\n"
        "2. Look for a confirmation email from the City of Munich "
        "(Landeshauptstadt München)\n"
        "3. <b>Click the confirmation link</b> in that email\n"
        "4. Your appointment will only be finalized after email confirmation\n\n"
        "If you don't see the email within 5 minutes, check your spam folder."
    ),
    "booking.failed": (
        "❌ <b>Booking Failed</b>\n\n"
        "The appointment could not be booked. Possible reasons:\n"
        "• The slot was just taken by someone else\n"
        "• Network error occurred\n"
        "• Captcha token expired\n\n"
        "Please try booking another available slot."
    ),
    "booking.watch_finished": "✅ I've stopped watching {service} for you.",
    "booking.will_update": "I'll keep watching and send you the current free slots.",
    "booking.error": (
        "❌ An error occurred while booking:\n{error}\n\n"
        "Please try again or contact support."
    ),
}
