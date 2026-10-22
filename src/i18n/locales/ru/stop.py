# ABOUTME: Russian texts for the /stop command.
# ABOUTME: Keys are "stop.<name>".

MESSAGES: dict[str, str | dict[str, str]] = {
    "stop.done": {
        "one": (
            "👋 Вы отписались, удалена {count} подписка.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
        "few": (
            "👋 Вы отписались, удалены {count} подписки.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
        "many": (
            "👋 Вы отписались, удалено {count} подписок.\n\n"
            "Чтобы зарегистрироваться снова, используйте /start."
        ),
    },
}
