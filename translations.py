"""
Multi-language support for the bot
Supports: German (DE), English (EN), Russian (RU)
"""
import os
import logging
import requests
import json

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Language codes
LANGUAGES = {
    'de': {'name': 'Deutsch', 'flag': '🇩🇪'},
    'en': {'name': 'English', 'flag': '🇬🇧'},
    'ru': {'name': 'Русский', 'flag': '🇷🇺'}
}

# Static translations for common bot messages
MESSAGES = {
    'welcome': {
        'de': """🎯 <b>München Termin Bot</b>

Willkommen! Ich benachrichtige Sie, wenn Termine verfügbar werden.

Befehle:
🤖 /ask - KI-Assistent (Fragen in natürlicher Sprache)
📋 /subscribe - Dienste nach Kategorie durchsuchen
📊 /myservices - Ihre Abonnements verwalten
📅 /setdates - Datumsbereich ändern
🌐 /language - Sprache ändern
📈 /stats - Bot-Statistiken
❌ /stop - Alle Abonnements kündigen

<b>Tipp:</b> Verwenden Sie /ask für schnelle Hilfe!
Beispiel: <code>/ask Ich brauche einen Aufenthaltstitel</code>""",
        'en': """🎯 <b>Munich Appointment Bot</b>

Welcome! I'll notify you when appointments become available.

Commands:
🤖 /ask - AI Assistant (natural language questions)
📋 /subscribe - Browse services by category
📊 /myservices - Manage your subscriptions
📅 /setdates - Change date range
🌐 /language - Change language
📈 /stats - Bot statistics
❌ /stop - Cancel all subscriptions

<b>Tip:</b> Use /ask for quick help!
Example: <code>/ask I need a residence permit</code>""",
        'ru': """🎯 <b>Мюнхенский бот записи</b>

Добро пожаловать! Я уведомлю вас, когда появятся свободные записи.

Команды:
🤖 /ask - AI-ассистент (вопросы на естественном языке)
📋 /subscribe - Просмотр услуг по категориям
📊 /myservices - Управление подписками
📅 /setdates - Изменить диапазон дат
🌐 /language - Сменить язык
📈 /stats - Статистика бота
❌ /stop - Отменить все подписки

<b>Совет:</b> Используйте /ask для быстрой помощи!
Пример: <code>/ask Мне нужен вид на жительство</code>"""
    },
    'language_select': {
        'de': '🌐 <b>Sprache wählen:</b>\n\nWählen Sie Ihre bevorzugte Sprache:',
        'en': '🌐 <b>Choose Language:</b>\n\nSelect your preferred language:',
        'ru': '🌐 <b>Выберите язык:</b>\n\nВыберите предпочитаемый язык:'
    },
    'language_changed': {
        'de': '✅ Sprache auf Deutsch geändert',
        'en': '✅ Language changed to English',
        'ru': '✅ Язык изменен на Русский'
    },
    'select_category': {
        'de': '📋 <b>Kategorie auswählen:</b>\n\nWählen Sie eine Kategorie, um verfügbare Dienste anzuzeigen:',
        'en': '📋 <b>Select Category:</b>\n\nChoose a category to view available services:',
        'ru': '📋 <b>Выберите категорию:</b>\n\nВыберите категорию для просмотра доступных услуг:'
    },
    'no_subscriptions': {
        'de': 'Sie haben keine aktiven Abonnements.\n\nVerwenden Sie /subscribe, um Dienste zu abonnieren.',
        'en': 'You have no active subscriptions.\n\nUse /subscribe to subscribe to services.',
        'ru': 'У вас нет активных подписок.\n\nИспользуйте /subscribe для подписки на услуги.'
    },
    'my_subscriptions': {
        'de': '📋 <b>Ihre Abonnements:</b>\n\n',
        'en': '📋 <b>Your Subscriptions:</b>\n\n',
        'ru': '📋 <b>Ваши подписки:</b>\n\n'
    },
    'total_subscriptions': {
        'de': '\n\nGesamt: {count} Abonnement(s)',
        'en': '\n\nTotal: {count} subscription(s)',
        'ru': '\n\nВсего: {count} подписок'
    },
    'subscribed': {
        'de': '✅ Abonniert!',
        'en': '✅ Subscribed!',
        'ru': '✅ Подписка оформлена!'
    },
    'service_not_found': {
        'de': '❌ Dienst nicht gefunden.',
        'en': '❌ Service not found.',
        'ru': '❌ Услуга не найдена.'
    },
    'no_services_in_category': {
        'de': '❌ Keine Dienste in dieser Kategorie gefunden.',
        'en': '❌ No services found in this category.',
        'ru': '❌ В этой категории не найдено услуг.'
    },
    'services_pagination': {
        'de': 'Dienste {start}-{end} von {total}:\n\nWählen Sie einen Dienst zum Abonnieren:',
        'en': 'Services {start}-{end} of {total}:\n\nSelect a service to subscribe:',
        'ru': 'Услуги {start}-{end} из {total}:\n\nВыберите услугу для подписки:'
    },
    'processing_question': {
        'de': '🔍 <b>Ihre Frage wird bearbeitet...</b>',
        'en': '🔍 <b>Processing your question...</b>',
        'ru': '🔍 <b>Обрабатываем ваш вопрос...</b>'
    },
    'no_matching_services': {
        'de': '❌ Ich konnte keine passenden Dienste finden.\n\nVersuchen Sie /subscribe, um alle Kategorien zu durchsuchen.',
        'en': '❌ I couldn\'t find any matching services.\n\nTry /subscribe to browse all categories.',
        'ru': '❌ Не удалось найти подходящие услуги.\n\nПопробуйте /subscribe для просмотра всех категорий.'
    },
    'matching_services_found': {
        'de': '🎯 <b>Passende Dienste gefunden:</b>\n\n',
        'en': '🎯 <b>Matching Services Found:</b>\n\n',
        'ru': '🎯 <b>Найдены подходящие услуги:</b>\n\n'
    },
    'tap_service_details': {
        'de': '\n💡 Tippen Sie auf einen Dienst für Details und Abonnement.',
        'en': '\n💡 Tap a service for details and subscription.',
        'ru': '\n💡 Нажмите на услугу для подробностей и подписки.'
    },
    'information_header': {
        'de': 'ℹ️ <b>Information</b>\n\n',
        'en': 'ℹ️ <b>Information</b>\n\n',
        'ru': 'ℹ️ <b>Информация</b>\n\n'
    },
    'more_questions': {
        'de': '📞 Weitere Fragen? Rufen Sie die <b>115</b> an.\n🌐 Oder besuchen Sie: https://stadt.muenchen.de',
        'en': '📞 More questions? Call <b>115</b>.\n🌐 Or visit: https://stadt.muenchen.de',
        'ru': '📞 Дополнительные вопросы? Позвоните <b>115</b>.\n🌐 Или посетите: https://stadt.muenchen.de'
    },
    'translate_to': {
        'de': 'Übersetzen nach',
        'en': 'Translate to',
        'ru': 'Перевести на'
    },
    'no_answer_found': {
        'de': 'ℹ️ Ich konnte keine spezifische Antwort finden.\n\n📞 Bitte rufen Sie die <b>115</b> für offizielle Auskünfte an.\n🌐 Oder besuchen Sie: https://stadt.muenchen.de',
        'en': 'ℹ️ I couldn\'t find a specific answer.\n\n📞 Please call <b>115</b> for official information.\n🌐 Or visit: https://stadt.muenchen.de',
        'ru': 'ℹ️ Не удалось найти конкретный ответ.\n\n📞 Позвоните <b>115</b> для получения официальной информации.\n🌐 Или посетите: https://stadt.muenchen.de'
    },
    'ask_help': {
        'de': """🤖 <b>KI-Assistent</b>

Stellen Sie Ihre Frage in natürlicher Sprache:

<b>Beispiele:</b>
• /ask Ich brauche einen Termin für meinen Aufenthaltstitel
• /ask Wie melde ich mein Auto um?
• /ask Welche Dokumente brauche ich für die Eheschließung?
• /ask Ich bin neu in München und brauche einen Termin

Der Bot schlägt passende Dienste vor oder beantwortet Ihre Frage.""",
        'en': """🤖 <b>AI Assistant</b>

Ask your question in natural language:

<b>Examples:</b>
• /ask I need an appointment for my residence permit
• /ask How do I register my car?
• /ask What documents do I need for marriage registration?
• /ask I'm new in Munich and need an appointment

The bot will suggest matching services or answer your question.""",
        'ru': """🤖 <b>AI-ассистент</b>

Задайте свой вопрос на естественном языке:

<b>Примеры:</b>
• /ask Мне нужна запись для вида на жительство
• /ask Как зарегистрировать машину?
• /ask Какие документы нужны для регистрации брака?
• /ask Я новичок в Мюнхене и мне нужна запись

Бот предложит подходящие услуги или ответит на ваш вопрос."""
    },
    'service_subscription_item': {
        'de': '✅ {name}\n   Service ID: {id}\n   Seit: {date}',
        'en': '✅ {name}\n   Service ID: {id}\n   Since: {date}',
        'ru': '✅ {name}\n   ID услуги: {id}\n   С: {date}'
    },
    'unsubscribed': {
        'de': '🗑 Abonnement gekündigt',
        'en': '🗑 Subscription cancelled',
        'ru': '🗑 Подписка отменена'
    },
    'appointment_available': {
        'de': '🎉 <b>TERMIN VERFÜGBAR!</b> 🎉',
        'en': '🎉 <b>APPOINTMENT AVAILABLE!</b> 🎉',
        'ru': '🎉 <b>ЗАПИСЬ ДОСТУПНА!</b> 🎉'
    },
    'available_slots': {
        'de': 'Verfügbare Termine:',
        'en': 'Available slots:',
        'ru': 'Доступные записи:'
    },
    'book_now': {
        'de': 'Jetzt Termin buchen!',
        'en': 'Book appointment now!',
        'ru': 'Записаться сейчас!'
    },
    'act_fast': {
        'de': '⚡ Schnell handeln - Termine werden schnell vergeben!',
        'en': '⚡ Act fast - appointments fill up quickly!',
        'ru': '⚡ Действуйте быстро - места быстро заканчиваются!'
    },
    'translate_to': {
        'de': '🌐 Übersetzen nach {lang}',
        'en': '🌐 Translate to {lang}',
        'ru': '🌐 Перевести на {lang}'
    },
    'translation_disclaimer': {
        'de': '\n\n⚠️ <i>Automatische Übersetzung - kann Fehler enthalten</i>',
        'en': '\n\n⚠️ <i>Automatic translation - may contain errors</i>',
        'ru': '\n\n⚠️ <i>Автоматический перевод - может содержать ошибки</i>'
    },
    'categories_button': {
        'de': '🏠 Kategorien',
        'en': '🏠 Categories',
        'ru': '🏠 Категории'
    },
    'subscribe_button': {
        'de': '✅ Abonnieren',
        'en': '✅ Subscribe',
        'ru': '✅ Подписаться'
    },
    'unsubscribe_button': {
        'de': '🗑 Abonnement kündigen',
        'en': '🗑 Unsubscribe',
        'ru': '🗑 Отменить подписку'
    },
    'back_button': {
        'de': '◀️ Zurück',
        'en': '◀️ Back',
        'ru': '◀️ Назад'
    },
    'status': {
        'de': 'Status: {status}',
        'en': 'Status: {status}',
        'ru': 'Статус: {status}'
    },
    'subscribed_status': {
        'de': '✅ Abonniert',
        'en': '✅ Subscribed',
        'ru': '✅ Подписка оформлена'
    },
    'not_subscribed_status': {
        'de': '⭕ Nicht abonniert',
        'en': '⭕ Not subscribed',
        'ru': '⭕ Нет подписки'
    }
}


def get_message(key: str, lang: str = 'de', **kwargs) -> str:
    """Get translated message"""
    msg = MESSAGES.get(key, {}).get(lang, MESSAGES.get(key, {}).get('de', ''))
    if kwargs:
        msg = msg.format(**kwargs)
    return msg


async def translate_text(text: str, target_lang: str, source_lang: str = 'de') -> str:
    """
    Translate text using OpenAI API

    Args:
        text: Text to translate
        target_lang: Target language code (en, de, ru)
        source_lang: Source language code

    Returns:
        Translated text
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, translation unavailable")
        return text

    lang_names = {
        'de': 'German',
        'en': 'English',
        'ru': 'Russian'
    }

    source_name = lang_names.get(source_lang, 'German')
    target_name = lang_names.get(target_lang, 'English')

    system_prompt = f"""You are a professional translator. Translate the following text from {source_name} to {target_name}.
Maintain the original formatting, including HTML tags like <b>, <i>, <code>, <a>.
Keep technical terms and service names in the original language when appropriate.
Preserve all URLs and links exactly as they are."""

    try:
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': OPENAI_MODEL,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': text}
            ],
            'temperature': 0.3,
            'max_tokens': 1000
        }

        logger.info(f"Translating text from {source_lang} to {target_lang}")
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        translated = result['choices'][0]['message']['content']

        logger.info("Translation completed successfully")
        return translated

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return text  # Return original on error


def get_language_name(lang_code: str) -> str:
    """Get language display name"""
    return LANGUAGES.get(lang_code, {}).get('name', 'Deutsch')


def get_language_flag(lang_code: str) -> str:
    """Get language flag emoji"""
    return LANGUAGES.get(lang_code, {}).get('flag', '🇩🇪')
