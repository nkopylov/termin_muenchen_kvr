# ABOUTME: Russian texts for inline button screens in handlers/buttons.py.
# ABOUTME: Keys are "buttons.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "buttons.menu_text": "🏠 <b>Главное меню</b>\n\nВыберите действие:",
    "buttons.btn_subscribe_termins": "📋 Подписаться на свободные записи",
    "buttons.btn_my_subscriptions": "📊 Мои подписки",
    "buttons.btn_set_dates": "📅 Выбрать период дат",
    "buttons.btn_status": "ℹ️ Статус подписки",
    "buttons.not_registered": (
        "❌ Вы не зарегистрированы.\n\nЧтобы зарегистрироваться, отправьте /start."
    ),
    "buttons.seconds_ago": {
        "one": "{count} секунду назад",
        "few": "{count} секунды назад",
        "many": "{count} секунд назад",
    },
    "buttons.minutes_ago": {
        "one": "{count} минуту назад",
        "few": "{count} минуты назад",
        "many": "{count} минут назад",
    },
    "buttons.hours_ago": {
        "one": "{count} час назад",
        "few": "{count} часа назад",
        "many": "{count} часов назад",
    },
    "buttons.next_check_seconds": {
        "one": "через ~{count} секунду",
        "few": "через ~{count} секунды",
        "many": "через ~{count} секунд",
    },
    "buttons.next_check_minutes": {
        "one": "через ~{count} минуту",
        "few": "через ~{count} минуты",
        "many": "через ~{count} минут",
    },
    "buttons.never": "ещё не проводилась",
    "buttons.soon": "скоро",
    "buttons.today": "сегодня",
    "buttons.yesterday": "вчера",
    "buttons.days_ago": {
        "one": "{count} день назад",
        "few": "{count} дня назад",
        "many": "{count} дней назад",
    },
    "buttons.recently": "недавно",
    "buttons.status_found": "\n🎯 Найдено записей: {found} (последняя: {latest})",
    "buttons.status_found_none": "\n🎯 Найдено записей: 0",
    "buttons.status": (
        "📊 <b>Ваш статус</b>\n\n"
        "👤 ID пользователя: <code>{user_id}</code>\n"
        "📋 Подписки: <b>{num_subs}</b>\n"
        "📅 Период дат: {start_date} — {end_date}\n"
        "🌐 Язык: {language}\n\n"
        "🔍 Последняя проверка: {last_check}\n"
        "⏱ Следующая проверка: {next_check}\n"
        "⚙️ Интервал проверки: {check_interval}"
        "{stats_line}\n\n"
        "👥 Всего пользователей: <b>{total_users}</b>"
    ),
    "buttons.setdates": (
        "📅 <b>Выбор периода дат</b>\n\n"
        "Текущий период: <b>{start_date}</b> — <b>{end_date}</b>\n\n"
        "Выберите готовый период или укажите свой:\n\n"
        "<b>Свой период:</b>\n"
        "<code>/setdates ГГГГ-ММ-ДД ГГГГ-ММ-ДД</code>\n\n"
        "<b>Пример:</b> <code>/setdates 2025-10-01 2025-10-31</code>"
    ),
    "buttons.preset_2_days": "📅 Ближайшие 2 дня ({today} — {end_date})",
    "buttons.preset_week": "📅 Ближайшая неделя ({today} — {end_date})",
    "buttons.preset_30_days": "📅 Ближайшие 30 дней ({today} — {end_date})",
    "buttons.preset_3_months": "📅 Ближайшие 3 месяца ({today} — {end_date})",
    "buttons.preset_6_months": "📅 Ближайшие 6 месяцев ({today} — {end_date})",
    "buttons.date_range_set": {
        "one": "✅ Период дат задан: ближайший {count} день",
        "few": "✅ Период дат задан: ближайшие {count} дня",
        "many": "✅ Период дат задан: ближайшие {count} дней",
    },
    "buttons.no_services_in_category": "❌ В категории «{category}» услуги не найдены.",
    "buttons.btn_previous": "◀️ Назад",
    "buttons.btn_next": "Далее ▶️",
    "buttons.pagination": "Услуги {first}–{last} из {total}",
    "buttons.service_not_found": "❌ Услуга не найдена.",
    "buttons.service_details": "<b>{name}</b>\n\nID услуги: <code>{service_id}</code>\n",
    "buttons.max_quantity": "Макс. количество: {max_quantity}\n",
    "buttons.service_status": "\nСтатус: {status}",
    "buttons.subscribed": "✅ Подписка оформлена",
    "buttons.not_subscribed": "⭕ Нет подписки",
    "buttons.btn_unsubscribe": "🗑 Отписаться",
    "buttons.btn_subscribe": "✅ Подписаться",
    "buttons.btn_back": "◀️ Назад",
    "buttons.btn_categories": "🏠 Категории",
    "buttons.no_offices": "❌ Для «{service}» не найдено ни одного отделения.",
    "buttons.select_office": (
        "<b>{service}</b>\n\n📍 Выберите отделение:\n(доступно: {available})"
    ),
    "buttons.office_fallback": "Отделение {office_id}",
    "buttons.offices_truncated": (
        "\n\n⚠️ Показаны только первые 20 отделений (всего: {total})."
    ),
    "buttons.no_subscriptions": (
        "📋 <b>Нет подписок</b>\n\n"
        "Вы пока не подписаны ни на одну услугу.\n"
        "Используйте /subscribe, чтобы начать отслеживать свободные записи!"
    ),
    "buttons.subscriptions_header": (
        "📋 <b>Ваши подписки</b>\n\nВы отслеживаете эти услуги:\n\n"
    ),
    "buttons.unknown_office": "Неизвестное отделение",
    "buttons.subscription_item": (
        "• <b>{service}</b>\n   📍 {office}\n   📅 Подписка оформлена: {subscribed_at}\n\n"
    ),
    "buttons.subscriptions_total": {
        "one": "<b>Всего:</b> {count} подписка",
        "few": "<b>Всего:</b> {count} подписки",
        "many": "<b>Всего:</b> {count} подписок",
    },
    "buttons.btn_unsubscribe_all": "🗑 Отписаться от всех",
    "buttons.booking_interrupted": (
        "❌ Процесс записи прервался (бот был перезапущен).\n\n"
        "Пожалуйста, начните запись заново из уведомления о свободной записи."
    ),
    "buttons.select_category": "📋 <b>Выберите категорию:</b>",
    "buttons.subscription_success": (
        "🎉 <b>Подписка оформлена!</b>\n\n"
        "<b>{service}</b>\n"
        "📍 Отделение: {office}\n\n"
        "📅 Вы получите уведомление, когда появятся свободные записи "
        "в период с <b>{start_date}</b> по <b>{end_date}</b>.\n\n"
        "💡 Совет: период дат можно изменить в любой момент командой /setdates!"
    ),
    "buttons.subscription_failed": "❌ Не удалось оформить подписку",
    "buttons.unsubscribed": "🗑 Подписка отменена",
    "buttons.unsub_all_confirm": (
        "⚠️ <b>Отписаться от всех услуг?</b>\n\n"
        "Все ваши подписки будут удалены. Вы сможете подписаться снова в любой момент.\n\n"
        "Вы уверены?"
    ),
    "buttons.btn_yes_remove_all": "✅ Да, удалить все",
    "buttons.btn_cancel": "❌ Отмена",
    "buttons.removed_subscriptions": {
        "one": "🗑 Удалена {count} подписка",
        "few": "🗑 Удалено {count} подписки",
        "many": "🗑 Удалено {count} подписок",
    },
}
