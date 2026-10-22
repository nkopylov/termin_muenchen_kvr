# ABOUTME: Russian texts for the booking conversation.
# ABOUTME: Keys are "booking.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "booking.fetching_slots": (
        "📅 Выбранная дата: {date}\n\nЗагружаю свободное время..."
    ),
    "booking.select_time": "📅 Свободное время на {date}:\n\nВыберите время:",
    "booking.invalid_data": (
        "❌ Некорректные данные записи. Пожалуйста, попробуйте снова."
    ),
    "booking.watch_ended": (
        "Этот поиск уже завершён. Начните новый через 🔎 Найти запись."
    ),
    "booking.day_gone": "😕 На {date} свободного времени больше нет.",
    "booking.times_failed": "⚠️ Сейчас не удалось загрузить время на {date}.",
    "booking.will_send_days": (
        "Я продолжаю искать и пришлю обновлённый список свободных дней."
    ),
    "booking.use_saved": (
        "🕐 {time}\n"
        "📍 {office}\n\n"
        "Записаться с сохранёнными данными?\n"
        "👤 {name}\n"
        "📧 {email}"
    ),
    "booking.btn_yes_book": "✅ Да, записаться",
    "booking.btn_change": "✏️ Ввести другие данные",
    "booking.btn_cancel": "❌ Отмена",
    "booking.btn_cancel_booking": "❌ Отменить запись",
    "booking.btn_confirm": "✅ Подтвердить запись",
    "booking.cancelled": "❌ Запись отменена.",
    "booking.session_cleared": (
        "❌ Время на оформление записи истекло, или процесс был сброшен.\n\n"
        "Пожалуйста, начните запись заново из уведомления о свободной записи."
    ),
    "booking.time_on_date": "{date} в {time}",
    "booking.time_on_long_date": "{weekday}, {day} {month} {year}, {time}",
    "booking.weekday_0": "понедельник",
    "booking.weekday_1": "вторник",
    "booking.weekday_2": "среда",
    "booking.weekday_3": "четверг",
    "booking.weekday_4": "пятница",
    "booking.weekday_5": "суббота",
    "booking.weekday_6": "воскресенье",
    "booking.month_1": "января",
    "booking.month_2": "февраля",
    "booking.month_3": "марта",
    "booking.month_4": "апреля",
    "booking.month_5": "мая",
    "booking.month_6": "июня",
    "booking.month_7": "июля",
    "booking.month_8": "августа",
    "booking.month_9": "сентября",
    "booking.month_10": "октября",
    "booking.month_11": "ноября",
    "booking.month_12": "декабря",
    "booking.ask_name": (
        "✅ Выбранное время: {time}\n\nВведите имя и фамилию (как в документах):"
    ),
    "booking.name_not_full": (
        "❌ Пожалуйста, введите имя и фамилию.\n\nПример: Ivan Petrov"
    ),
    "booking.name_too_short": (
        "❌ Имя слишком короткое. Пожалуйста, введите имя и фамилию:"
    ),
    "booking.ask_email": (
        "✅ Имя: {name}\n\n"
        "Введите ваш адрес электронной почты "
        "(на него придёт письмо с подтверждением):"
    ),
    "booking.email_invalid": (
        "❌ Некорректный адрес электронной почты. "
        "Пожалуйста, введите правильный адрес:\n\n"
        "Пример: your.name@example.com"
    ),
    "booking.confirm_summary": (
        "📋 <b>Пожалуйста, подтвердите запись:</b>\n\n"
        "🕐 Время: {time}\n"
        "👤 Имя: {name}\n"
        "📧 Эл. почта: {email}\n\n"
        "<b>Важно:</b> вам придёт письмо с подтверждением. "
        "Обязательно перейдите по ссылке в этом письме, "
        "чтобы окончательно подтвердить запись!"
    ),
    "booking.processing": "⏳ Оформляю запись...\nЭто может занять несколько секунд.",
    "booking.success": (
        "🎉 <b>Запись оформлена!</b> 🎉\n\n"
        "📋 Номер записи: {process_id}\n"
        "🕐 Время: {time}\n"
        "👤 Имя: {name}\n"
        "📧 Эл. почта: {email}\n\n"
        "<b>⚠️ ВАЖНО — что делать дальше:</b>\n\n"
        "1. Проверьте почтовый ящик <b>{email}</b>\n"
        "2. Найдите письмо с подтверждением от города Мюнхена "
        "(Landeshauptstadt München)\n"
        "3. <b>Перейдите по ссылке для подтверждения</b> в этом письме\n"
        "4. Запись будет окончательно оформлена только после подтверждения "
        "по электронной почте\n\n"
        "Если письмо не пришло в течение 5 минут, проверьте папку «Спам»."
    ),
    "booking.failed": (
        "❌ <b>Запись не удалась</b>\n\n"
        "Не удалось оформить запись. Возможные причины:\n"
        "• это время только что занял кто-то другой\n"
        "• произошла ошибка сети\n"
        "• истёк срок действия капчи\n\n"
        "Пожалуйста, попробуйте выбрать другое свободное время."
    ),
    "booking.watch_finished": "✅ Поиск «{service}» завершён.",
    "booking.will_update": ("Я продолжаю искать и пришлю актуальные свободные записи."),
    "booking.error": (
        "❌ При оформлении записи произошла ошибка:\n{error}\n\n"
        "Пожалуйста, попробуйте снова или обратитесь в поддержку."
    ),
}
