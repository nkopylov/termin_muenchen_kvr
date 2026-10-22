# ABOUTME: Tests for service categories: short ASCII ids, grouping of the city catalog by id,
# ABOUTME: and the English and Russian category labels.

import pytest

from src import services_manager
from src.i18n import t
from src.services_manager import (
    CATEGORY_KEYWORDS,
    categorize_services,
    get_category_for_service,
)

ENGLISH_LABELS = {
    "auslaenderbehoerde": "Ausländerbehörde 🌍",
    "ausweis": "ID card & passport 🆔",
    "fahrzeug": "Vehicles 🚗",
    "fuehrerschein": "Driving licence 🪪",
    "wohnsitz": "Residence & address 🏠",
    "gewerbe": "Business 💼",
    "familie": "Family 👨‍👩‍👧",
    "soziales": "Pension & social 🏥",
    "parken": "Parking 🅿️",
    "sonstiges": "Other 📋",
}

SERVICES = [
    {"id": 1, "name": "Aufenthaltstitel - Verlängerung", "maxQuantity": 1},
    {"id": 2, "name": "Kfz-Zulassung", "maxQuantity": 3},
    {"id": 3, "name": "Hundesteuer"},
    *[
        {"id": 100 + i, "name": f"Führerschein Klasse {i:02d}", "maxQuantity": 1}
        for i in range(11)
    ],
]


@pytest.fixture(autouse=True)
def city_catalog(monkeypatch):
    monkeypatch.setattr(services_manager, "_services_cache", SERVICES)
    monkeypatch.setattr(
        services_manager,
        "_full_payload_cache",
        {"services": SERVICES, "offices": [], "relations": []},
    )


class TestCategoryIds:
    def test_category_ids_are_short_ascii(self):
        assert list(CATEGORY_KEYWORDS) == list(ENGLISH_LABELS)
        for category_id in CATEGORY_KEYWORDS:
            assert category_id.isascii()
            assert len(f"catpage:{category_id}:999".encode()) <= 64

    def test_categorize_services_is_keyed_by_id(self):
        categories = categorize_services()
        assert [s["id"] for s in categories["auslaenderbehoerde"]] == [1]
        assert [s["id"] for s in categories["fahrzeug"]] == [2]
        assert [s["id"] for s in categories["sonstiges"]] == [3]
        assert len(categories["fuehrerschein"]) == 11
        assert set(categories) <= set(CATEGORY_KEYWORDS)

    def test_category_for_service_is_id(self):
        assert get_category_for_service(2) == "fahrzeug"
        assert get_category_for_service(3) == "sonstiges"
        assert get_category_for_service(999) is None

    def test_english_labels_unchanged(self):
        for category_id, label in ENGLISH_LABELS.items():
            assert t(f"categories.{category_id}", "en") == label

    def test_russian_labels(self):
        assert {cid: t(f"categories.{cid}", "ru") for cid in CATEGORY_KEYWORDS} == {
            "auslaenderbehoerde": "Ausländerbehörde 🌍",
            "ausweis": "Паспорт и ID-карта 🆔",
            "fahrzeug": "Автомобиль 🚗",
            "fuehrerschein": "Водительские права 🪪",
            "wohnsitz": "Место жительства 🏠",
            "gewerbe": "Бизнес 💼",
            "familie": "Семья 👨‍👩‍👧",
            "soziales": "Пенсия и соцпомощь 🏥",
            "parken": "Парковка 🅿️",
            "sonstiges": "Другое 📋",
        }
