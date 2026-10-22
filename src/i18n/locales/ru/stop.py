# ABOUTME: Russian texts for the /stop command.
# ABOUTME: Keys are "stop.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "stop.done": {
        "one": (
            "👋 Вы отписались от всех услуг. Удалена {count} подписка.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
        "few": (
            "👋 Вы отписались от всех услуг. Удалены {count} подписки.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
        "many": (
            "👋 Вы отписались от всех услуг. Удалено {count} подписок.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
    },
}
