# ABOUTME: Russian texts for the Settings screen and its buttons.
# ABOUTME: Keys are "settings.<name>"; {contact} is already HTML-escaped by the caller.

MESSAGES: dict[str, str | dict[str, str]] = {
    "settings.text": (
        "⚙️ <b>Настройки</b>\n\n🌐 Язык: {language}\n📇 Данные для записи: {contact}"
    ),
    "settings.contact_none": "пока не сохранены",
    "settings.btn_forget": "🧹 Забыть данные для записи",
    "settings.btn_delete": "🗑 Удалить мои данные",
    "settings.forgotten": "Данные для записи удалены.",
}
