# ABOUTME: Russian texts for the /help command.
# ABOUTME: Keys are "help.<name>"; {find} is the reply keyboard's Find label.

MESSAGES: dict[str, str | dict[str, str]] = {
    "help.text": (
        "❓ <b>Как это работает</b>\n\n"
        "1. Скажите, что вам нужно: нажмите {find} или просто напишите, "
        "например, «паспорт».\n"
        "2. Выберите отделение и когда вам нужна запись.\n"
        "3. Я круглосуточно проверяю календарь записи и напишу вам, "
        "как только появится свободное время.\n"
        "4. Запишитесь прямо в чате или на сайте города.\n\n"
        "<b>Команды</b>\n"
        "/find — найти запись\n"
        "/watches — мои поиски\n"
        "/settings — язык, сохранённые данные для записи, удаление данных\n"
        "/language — сменить язык\n"
        "/stop — удалить мои данные\n"
        "/help — эта справка\n\n"
        "Нашли ошибку? https://github.com/nkopylov/termin_muenchen_kvr"
    ),
}
