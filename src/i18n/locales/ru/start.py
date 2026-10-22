# ABOUTME: Russian texts for /start: the welcome, the returning-user greeting and the menu announcement.
# ABOUTME: Keys are "start.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "start.welcome": (
        "👋 <b>Здравствуйте! Я ищу свободные записи (Termin) в ведомствах Мюнхена.</b>\n"
        "Скажите, что вам нужно, и я напишу, как только появится свободное время. "
        "Меню — внизу чата."
    ),
    "start.welcome_back": "👋 <b>С возвращением!</b>\nМеню — внизу чата.",
    "start.not_registered": (
        "👋 Добро пожаловать! Сначала зарегистрируйтесь с помощью /start."
    ),
    "start.announce": (
        "🆕 <b>У бота новое меню</b>\n"
        "Ваши подписки теперь называются <b>поисками</b>: откройте {watches}, "
        "чтобы посмотреть их, изменить время или поставить на паузу. "
        "Меню — внизу чата."
    ),
}
