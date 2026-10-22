# ABOUTME: Russian texts for the /myservices command.
# ABOUTME: Keys are "myservices.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "myservices.empty": (
        "📋 <b>Нет подписок</b>\n\nВы пока не подписаны ни на одну услугу.\n"
        "Используйте /subscribe, чтобы начать отслеживать свободные записи!"
    ),
    "myservices.header": "📋 <b>Ваши подписки</b>\n\nВы отслеживаете эти услуги:\n\n",
    "myservices.item": (
        "• <b>{service}</b>\n   📍 {office}\n   📅 Подписка оформлена: {date}\n\n"
    ),
    "myservices.unknown_office": "Неизвестное отделение",
    "myservices.total": {
        "one": "<b>Всего:</b> {count} подписка",
        "few": "<b>Всего:</b> {count} подписки",
        "many": "<b>Всего:</b> {count} подписок",
    },
    "myservices.btn_subscribe_more": "📋 Подписаться ещё",
    "myservices.btn_unsubscribe_all": "🗑 Отписаться от всех",
}
