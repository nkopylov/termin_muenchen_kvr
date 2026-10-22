# ABOUTME: Russian texts for the My watches screen and its buttons.
# ABOUTME: Keys are "watches.<name>"; {summary} is already HTML-escaped by the caller.

MESSAGES: dict[str, str | dict[str, str]] = {
    "watches.header": "👀 <b>Мои поиски</b> ({count} из {limit})",
    "watches.header_over": "👀 <b>Мои поиски</b> ({count})",
    "watches.line": "<b>{n}.</b> {summary}\n      {state}{checked}",
    "watches.checked": " · проверено {ago}",
    "watches.empty": (
        "👀 <b>Мои поиски</b>\n\n"
        "Сейчас у вас нет поисков. Скажите, что вам нужно, "
        "и я поищу свободную запись."
    ),
    "watches.btn_time": "{n}. 🕒 Время",
    "watches.btn_pause": "⏸ Пауза",
    "watches.btn_resume": "▶️ Продолжить",
    "watches.btn_stop": "⏹ Стоп",
    "watches.btn_again": "{n}. 🔁 Искать снова",
    "watches.btn_any_office": "{n}. 🏢 Любое отделение",
    "watches.btn_new": "➕ Новый поиск",
    "watches.btn_find": "🔎 Найти запись",
    "watches.stop_confirm": (
        "⏹ <b>Остановить этот поиск?</b>\n{summary}\n\n"
        "Я перестану искать для него свободные записи."
    ),
    "watches.btn_stop_yes": "⏹ Да, остановить",
    "watches.btn_stop_no": "↩️ Нет, продолжить",
    "watches.not_open": "Этот поиск уже завершён.",
}
