# ABOUTME: Russian texts for deleting all of a user's data (/stop and Settings).
# ABOUTME: Keys are "stop.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "stop.confirm": (
        "🗑 <b>Удалить все ваши данные?</b>\n\n"
        "Я остановлю все ваши поиски и забуду ваш язык и сохранённые данные "
        "для записи. Это действие нельзя отменить."
    ),
    "stop.btn_yes": "🗑 Да, удалить",
    "stop.btn_no": "↩️ Нет, оставить",
    "stop.kept": "👍 Ничего не удалено.",
    "stop.done": (
        "👋 Готово. Я удалил все ваши данные и остановил все поиски.\n"
        "Если захотите снова воспользоваться ботом, отправьте /start."
    ),
}
