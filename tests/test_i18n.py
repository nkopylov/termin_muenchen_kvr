# ABOUTME: Tests for the translation layer: lookup, placeholders, plural rules, fallback.
# ABOUTME: Also checks catalog integrity (duplicate keys, en/ru parity, HTML tag balance).

import logging
import re
import string
import types

import pytest

from src import i18n
from src.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    is_language_chosen,
    merge_catalogs,
    normalize_language,
    plural_form,
    t,
)


def _module(name: str, messages: dict) -> types.ModuleType:
    module = types.ModuleType(name)
    module.MESSAGES = messages
    return module


def _fields(message: str | dict[str, str]) -> set[str]:
    forms = message.values() if isinstance(message, dict) else [message]
    return {
        field
        for form in forms
        for _, field, _, _ in string.Formatter().parse(form)
        if field
    }


class TestLanguageValues:
    def test_supported_languages(self):
        assert SUPPORTED_LANGUAGES == ("en", "ru")
        assert DEFAULT_LANGUAGE == "en"

    @pytest.mark.parametrize("value", ["en", "ru"])
    def test_normalize_keeps_supported(self, value):
        assert normalize_language(value) == value

    @pytest.mark.parametrize("value", ["", None, "de", "RU", "ru-RU", "xx"])
    def test_normalize_falls_back_to_english(self, value):
        assert normalize_language(value) == "en"

    @pytest.mark.parametrize("value", ["en", "ru"])
    def test_is_language_chosen_true(self, value):
        assert is_language_chosen(value) is True

    @pytest.mark.parametrize("value", ["", None, "de"])
    def test_is_language_chosen_false(self, value):
        assert is_language_chosen(value) is False


class TestPluralRules:
    @pytest.mark.parametrize(
        ("count", "form"),
        [
            (0, "many"),
            (1, "one"),
            (2, "few"),
            (5, "many"),
            (11, "many"),
            (12, "many"),
            (14, "many"),
            (21, "one"),
            (22, "few"),
            (25, "many"),
            (101, "one"),
            (111, "many"),
        ],
    )
    def test_russian(self, count, form):
        assert plural_form("ru", count) == form

    @pytest.mark.parametrize(
        ("count", "form"),
        [(0, "other"), (1, "one"), (2, "other"), (5, "other"), (21, "other")],
    )
    def test_english(self, count, form):
        assert plural_form("en", count) == form


@pytest.fixture
def test_messages(monkeypatch):
    """Inject test-only keys into the real catalogs."""
    monkeypatch.setitem(
        i18n.CATALOGS["en"],
        "test.days",
        {"one": "{count} day", "other": "{count} days"},
    )
    monkeypatch.setitem(
        i18n.CATALOGS["ru"],
        "test.days",
        {"one": "{count} день", "few": "{count} дня", "many": "{count} дней"},
    )
    monkeypatch.setitem(i18n.CATALOGS["en"], "test.hello", "Hello, <b>{name}</b>!")
    monkeypatch.setitem(i18n.CATALOGS["ru"], "test.hello", "Привет, <b>{name}</b>!")
    monkeypatch.setitem(i18n.CATALOGS["en"], "test.only_en", "English only")


class TestTranslate:
    def test_placeholders(self, test_messages):
        assert t("test.hello", "en", name="Anna") == "Hello, <b>Anna</b>!"
        assert t("test.hello", "ru", name="Анна") == "Привет, <b>Анна</b>!"

    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "0 дней"),
            (1, "1 день"),
            (2, "2 дня"),
            (5, "5 дней"),
            (11, "11 дней"),
            (21, "21 день"),
            (22, "22 дня"),
            (25, "25 дней"),
            (101, "101 день"),
            (111, "111 дней"),
        ],
    )
    def test_russian_plural(self, test_messages, count, expected):
        assert t("test.days", "ru", count=count) == expected

    def test_english_plural(self, test_messages):
        assert t("test.days", "en", count=1) == "1 day"
        assert t("test.days", "en", count=3) == "3 days"

    @pytest.mark.parametrize("lang", ["", None, "de"])
    def test_unset_language_uses_english(self, test_messages, lang):
        assert t("test.hello", lang, name="X") == "Hello, <b>X</b>!"

    def test_missing_russian_falls_back_to_english_with_warning(
        self, test_messages, caplog
    ):
        with caplog.at_level(logging.WARNING, logger="src.i18n"):
            assert t("test.only_en", "ru") == "English only"
        assert any("test.only_en" in r.getMessage() for r in caplog.records)

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            t("test.does_not_exist", "en")

    def test_unknown_key_in_russian_raises(self, caplog):
        with (
            caplog.at_level(logging.WARNING, logger="src.i18n"),
            pytest.raises(KeyError),
        ):
            t("test.does_not_exist", "ru")
        assert any("test.does_not_exist" in r.getMessage() for r in caplog.records)

    def test_plural_without_count_raises(self, test_messages):
        with pytest.raises(KeyError):
            t("test.days", "en")


class TestMergeCatalogs:
    def test_merges_areas(self):
        merged = merge_catalogs(
            [_module("a", {"a.x": "1"}), _module("b", {"b.y": "2"})]
        )
        assert merged == {"a.x": "1", "b.y": "2"}

    def test_duplicate_key_raises(self):
        with pytest.raises(ValueError, match="a.x"):
            merge_catalogs([_module("a", {"a.x": "1"}), _module("b", {"a.x": "2"})])


class TestCatalogIntegrity:
    def test_same_keys_in_all_languages(self):
        en_keys = set(i18n.CATALOGS["en"])
        ru_keys = set(i18n.CATALOGS["ru"])
        assert sorted(en_keys - ru_keys) == []
        assert sorted(ru_keys - en_keys) == []

    def test_same_placeholders_in_all_languages(self):
        mismatched = [
            key
            for key, message in i18n.CATALOGS["en"].items()
            if key in i18n.CATALOGS["ru"]
            and _fields(message) != _fields(i18n.CATALOGS["ru"][key])
        ]
        assert mismatched == []

    @pytest.mark.parametrize(
        ("lang", "forms"),
        [("en", {"one", "other"}), ("ru", {"one", "few", "many"})],
    )
    def test_plural_messages_have_all_forms(self, lang, forms):
        wrong = [
            key
            for key, message in i18n.CATALOGS[lang].items()
            if isinstance(message, dict) and set(message) != forms
        ]
        assert wrong == []

    def test_russian_plural_forms_show_count(self):
        missing = [
            (key, form)
            for key, message in i18n.CATALOGS["ru"].items()
            if isinstance(message, dict)
            for form, text in message.items()
            if "{count}" not in text
        ]
        assert missing == []

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_html_tags_balanced(self, lang):
        unbalanced = []
        for key, message in i18n.CATALOGS[lang].items():
            forms = message.values() if isinstance(message, dict) else [message]
            for text in forms:
                opened = re.findall(r"<([a-z]+)[^>]*>", text)
                closed = re.findall(r"</([a-z]+)>", text)
                if sorted(opened) != sorted(closed):
                    unbalanced.append(key)
        assert unbalanced == []

    def test_keys_use_area_prefix(self):
        bad = [
            key
            for key in i18n.CATALOGS["en"]
            if not re.fullmatch(r"[a-z_]+\.[a-z0-9_.]+", key)
        ]
        assert bad == []
