# ABOUTME: Russian texts for the /status command.
# ABOUTME: Keys are "status.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "status.not_registered": (
        "❌ Вы не зарегистрированы.\n\nЧтобы зарегистрироваться, отправьте /start."
    ),
    "status.seconds_ago": {
        "one": "{count} секунду назад",
        "few": "{count} секунды назад",
        "many": "{count} секунд назад",
    },
    "status.minutes_ago": {
        "one": "{count} минуту назад",
        "few": "{count} минуты назад",
        "many": "{count} минут назад",
    },
    "status.hours_ago": {
        "one": "{count} час назад",
        "few": "{count} часа назад",
        "many": "{count} часов назад",
    },
    "status.next_in_seconds": {
        "one": "через ~{count} секунду",
        "few": "через ~{count} секунды",
        "many": "через ~{count} секунд",
    },
    "status.next_in_minutes": {
        "one": "через ~{count} минуту",
        "few": "через ~{count} минуты",
        "many": "через ~{count} минут",
    },
    "status.last_check_never": "ещё не проводилась",
    "status.next_check_soon": "скоро",
    "status.found_today": "сегодня",
    "status.found_yesterday": "вчера",
    "status.found_days_ago": {
        "one": "{count} день назад",
        "few": "{count} дня назад",
        "many": "{count} дней назад",
    },
    "status.found_recently": "недавно",
    "status.appointments_found": "\n🎯 Найдено записей: {found} (последняя: {latest})",
    "status.appointments_found_none": "\n🎯 Найдено записей: 0",
    "status.interval_seconds": {
        "one": "{count} секунда",
        "few": "{count} секунды",
        "many": "{count} секунд",
    },
    "status.message": (
        "📊 <b>Ваш статус</b>\n\n"
        "👤 ID пользователя: <code>{user_id}</code>\n"
        "📋 Подписки: <b>{num_subs}</b>\n"
        "📅 Период дат: {start_date} — {end_date}\n"
        "🌐 Язык: {language}\n\n"
        "🔍 Последняя проверка: {last_check}\n"
        "⏱ Следующая проверка: {next_check}\n"
        "⚙️ Интервал проверки: {check_interval}"
        "{stats_line}"
    ),
}
