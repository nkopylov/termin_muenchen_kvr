# ABOUTME: Russian texts for the /setdates command.
# ABOUTME: Keys are "setdates.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "setdates.btn_next_2_days": "📅 Ближайшие 2 дня ({start} — {end})",
    "setdates.btn_next_week": "📅 Ближайшая неделя ({start} — {end})",
    "setdates.btn_next_30_days": "📅 Ближайшие 30 дней ({start} — {end})",
    "setdates.btn_next_3_months": "📅 Ближайшие 3 месяца ({start} — {end})",
    "setdates.btn_next_6_months": "📅 Ближайшие 6 месяцев ({start} — {end})",
    "setdates.presets": (
        "📅 <b>Выбор периода дат</b>\n\n"
        "Выберите готовый период или укажите свой:\n\n"
        "<b>Свой период:</b>\n"
        "<code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
        "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.invalid_format": (
        "❌ Неверный формат.\n\n"
        "Использование: <code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
        "Пример:\n"
        "<code>/setdates 2025-10-01 2025-10-31</code>\n\n"
        "Или отправьте /setdates без параметров, чтобы выбрать готовый период."
    ),
    "setdates.invalid_range": (
        "❌ Неверный период дат. Дата окончания должна быть позже даты начала.\n\n"
        "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.invalid_date": (
        "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД\n\n"
        "Пример: <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "setdates.updated": (
        "✅ Период дат обновлён!\n\n"
        "Начало: <b>{start_date}</b>\n"
        "Окончание: <b>{end_date}</b>\n\n"
        "Теперь бот будет искать свободные записи в этом периоде дат."
    ),
}
