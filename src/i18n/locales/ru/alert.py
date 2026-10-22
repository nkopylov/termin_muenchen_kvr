# ABOUTME: Russian texts of watch alert messages in every lifecycle state and their buttons.
# ABOUTME: Keys are "alert.<name>"; {summary} is already HTML-escaped by the renderer.

MESSAGES: dict[str, str | dict[str, str]] = {
    "alert.slots": "🎉 <b>Есть свободные записи</b>\n{summary}\n\n📅 {day}: {times}{more}",
    "alert.also_free": "Ещё свободно: {days}",
    "alert.also_free_more": {
        "one": "Ещё свободно: {days} и ещё {count} день",
        "few": "Ещё свободно: {days} и ещё {count} дня",
        "many": "Ещё свободно: {days} и ещё {count} дней",
    },
    "alert.times_unknown": "время смотрите на сайте",
    "alert.updated_existing": "✏️ Я обновил ваш поиск по этой услуге.",
    "alert.none_yet": (
        "🔎 <b>Ищу запись</b>\n{summary}\n\n"
        "Свободных записей пока нет. Я напишу, как только появится."
    ),
    "alert.check_failed": (
        "🔎 <b>Ищу запись</b>\n{summary}\n\n"
        "Сейчас не получилось проверить. Я продолжу попытки и напишу, "
        "когда появятся записи."
    ),
    "alert.empty_now": (
        "🔎 <b>Ищу запись</b>\n{summary}\n\n"
        "😕 Сейчас свободных записей нет (на {time}). Продолжаю искать."
    ),
    "alert.outdated": "⌛ Устарело — смотрите новое сообщение ниже.",
    "alert.final_booked": "✅ <b>Вы записаны</b>\n{summary}\n\nЭтот поиск завершён.",
    "alert.final_stopped": "⏹ <b>Поиск остановлен</b>\n{summary}",
    "alert.final_paused": (
        "⏸ <b>Поиск на паузе</b>\n{summary}\n\nВозобновить его можно в «Мои поиски»."
    ),
    "alert.final_deadline": "⌛ <b>Поиск завершён</b>: срок прошёл.\n{summary}",
    "alert.final_gone": (
        "⚠️ <b>Поиск завершён</b>: это отделение больше не принимает онлайн-запись "
        "на эту услугу.\n{summary}"
    ),
    "alert.deadline": (
        "⌛ <b>Поиск завершён</b>\n{summary}\n\n"
        "Срок прошёл, а свободную запись я так и не нашёл."
    ),
    "alert.gone": (
        "⚠️ <b>Поиск завершён</b>\n{summary}\n\n"
        "Это отделение больше не принимает онлайн-запись на эту услугу."
    ),
    "alert.btn_book": "📅 Записаться: {day}",
    "alert.btn_website": "🌐 Сайт",
    "alert.btn_stop": "⏹ Остановить поиск",
    "alert.btn_extend": "🔁 Продлить",
    "alert.btn_new_search": "🔎 Новый поиск",
    "alert.btn_any_office": "🏢 Любое отделение",
    "alert.booking_timed_out": (
        "⌛ Время на запись истекло. Я пришлю актуальные свободные записи."
    ),
}
