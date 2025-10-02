"""
Modern i18n implementation using Babel/gettext
Type-safe translation keys and runtime language switching
"""
import gettext
from pathlib import Path
from typing import Dict, Optional
from enum import Enum
import logging
import requests
import json

from models import Language

logger = logging.getLogger(__name__)

# Translation directory
LOCALE_DIR = Path(__file__).parent / "locales"

# Language metadata for UI elements
LANGUAGE_INFO = {
    Language.DE: {'name': 'Deutsch', 'flag': '🇩🇪'},
    Language.EN: {'name': 'English', 'flag': '🇬🇧'},
    Language.RU: {'name': 'Русский', 'flag': '🇷🇺'}
}


class TranslationKey(str, Enum):
    """Type-safe translation keys"""
    # Welcome and basic
    WELCOME = "welcome"
    LANGUAGE_SELECT = "language_select"
    LANGUAGE_CHANGED = "language_changed"

    # Categories and services
    SELECT_CATEGORY = "select_category"
    NO_SERVICES_IN_CATEGORY = "no_services_in_category"
    SERVICES_PAGINATION = "services_pagination"
    SERVICE_NOT_FOUND = "service_not_found"

    # Subscriptions
    NO_SUBSCRIPTIONS = "no_subscriptions"
    MY_SUBSCRIPTIONS = "my_subscriptions"
    TOTAL_SUBSCRIPTIONS = "total_subscriptions"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    SERVICE_SUBSCRIPTION_ITEM = "service_subscription_item"

    # AI Assistant
    ASK_HELP = "ask_help"
    PROCESSING_QUESTION = "processing_question"
    NO_MATCHING_SERVICES = "no_matching_services"
    MATCHING_SERVICES_FOUND = "matching_services_found"
    TAP_SERVICE_DETAILS = "tap_service_details"

    # Information
    INFORMATION_HEADER = "information_header"
    MORE_QUESTIONS = "more_questions"
    NO_ANSWER_FOUND = "no_answer_found"
    TRANSLATE_TO = "translate_to"


class Translator:
    """
    Thread-safe translator with caching
    Uses gettext for production-ready i18n
    """

    def __init__(self):
        self._translations: Dict[Language, gettext.GNUTranslations] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load all translation catalogs"""
        for lang in Language:
            try:
                translation = gettext.translation(
                    'messages',
                    localedir=str(LOCALE_DIR),
                    languages=[lang.value],
                    fallback=True
                )
                self._translations[lang] = translation
                logger.info(f"Loaded translations for {lang.value}")
            except Exception as e:
                logger.warning(f"Failed to load translations for {lang.value}: {e}")
                # Create fallback
                self._translations[lang] = gettext.NullTranslations()

    def get(
        self,
        key: TranslationKey,
        lang: Language = Language.DE,
        **kwargs
    ) -> str:
        """
        Get translated string with optional formatting

        Args:
            key: Translation key
            lang: Target language
            **kwargs: Format arguments

        Returns:
            Translated and formatted string
        """
        translation = self._translations.get(lang, self._translations[Language.DE])
        text = translation.gettext(key.value)

        # Format if arguments provided
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing format key {e} for translation {key}")

        return text

    def ngettext(
        self,
        singular: str,
        plural: str,
        n: int,
        lang: Language = Language.DE
    ) -> str:
        """
        Get plural-aware translation

        Args:
            singular: Singular form
            plural: Plural form
            n: Count
            lang: Target language

        Returns:
            Appropriate plural form
        """
        translation = self._translations.get(lang, self._translations[Language.DE])
        return translation.ngettext(singular, plural, n)


# Global translator instance
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """Get or create the global translator instance"""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def _(
    key: TranslationKey,
    lang: Language = Language.DE,
    **kwargs
) -> str:
    """
    Shorthand translation function

    Args:
        key: Translation key
        lang: Target language
        **kwargs: Format arguments

    Returns:
        Translated string
    """
    return get_translator().get(key, lang, **kwargs)


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
    from config import get_config

    config = get_config()

    if not config.has_openai:
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
            'Authorization': f'Bearer {config.openai_api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': config.openai_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': text}
            ],
            'max_completion_tokens': 1000
        }

        logger.info(f"Translating text from {source_lang} to {target_lang}")
        logger.debug(f"OpenAI request payload: {json.dumps(payload, ensure_ascii=False)}")

        response = requests.post(config.openai_api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        translated = result['choices'][0]['message']['content']

        logger.info("Translation completed successfully")
        return translated

    except requests.exceptions.HTTPError as e:
        logger.error(f"Translation failed: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        return text
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        logger.error(f"Request payload: {json.dumps(payload, ensure_ascii=False)}")
        return text
