# ABOUTME: Russian texts for appointment notifications.
# ABOUTME: Keys are "notify.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "notify.initial": (
        "🎉 <b>ЕСТЬ СВОБОДНАЯ ЗАПИСЬ!</b> 🎉\n\n"
        "<b>{service_name}</b>\n\n"
        "Свободные записи:\n{dates}\n\n"
        "🔗 <a href='{booking_url}'>Записаться сейчас!</a>\n\n"
        "⏳ Загружаем свободное время..."
    ),
    "notify.final": (
        "🎉 <b>ЕСТЬ СВОБОДНАЯ ЗАПИСЬ!</b> 🎉\n\n"
        "<b>{service_name}</b>\n\n"
        "Свободные записи:\n{dates}\n\n"
        "🔗 <a href='{booking_url}'>Записаться сейчас!</a>\n\n"
        "⚡ Поторопитесь — записи быстро разбирают!"
    ),
    "notify.more_days": {
        "one": "... и ещё {count} день",
        "few": "... и ещё {count} дня",
        "many": "... и ещё {count} дней",
    },
    "notify.unknown_date": "Дата неизвестна",
    "notify.btn_book_date": "📅 Записаться: {date}",
    "notify.btn_book_manually": "🔗 Записаться вручную на сайте",
}
