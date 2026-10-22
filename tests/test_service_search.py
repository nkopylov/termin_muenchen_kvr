# ABOUTME: Tests for the service search: normalization, synonyms in English/Russian/German, ranking.
# ABOUTME: Runs against the test catalog's service list; no database or network.

import pytest

from src.services.service_search import SYNONYMS, normalize, search_services
from src.watches.labels import POPULAR_SERVICE_IDS
from tests.conftest import CATALOG_SERVICES

PASSPORT = 1063453
ID_CARD = 1063441
ANMELDUNG = 1063475
LICENCE = 1071896
CAR_DEREG = 1064305
URGENT_WORK = 10339028
URGENT_STUDY = 10339027
EAT_PICKUP = 10502137
GEWERBE = 1063423
EINBUERGERUNG = 1071907
PARKING = 1072043


def ids(query: str, services=CATALOG_SERVICES, limit: int = 8) -> list[int]:
    return [s["id"] for s in search_services(query, services, limit)]


class TestNormalize:
    @pytest.mark.parametrize("text", ["Führerschein", "fuehrerschein", "fuhrerschein"])
    def test_umlaut_variants_are_equal(self, text):
        assert normalize(text) == "fuhrerschein"

    def test_sharp_s_and_yo(self):
        assert normalize("Straße") == "strasse"
        assert normalize("Учёт") == "учет"

    def test_casefold_and_split_on_punctuation(self):
        assert (
            normalize("  Gewerbe-Anmeldung (Vor-Ort) ") == "gewerbe anmeldung vor ort"
        )

    def test_digraphs_after_umlauts(self):
        assert normalize("Böse") == normalize("Boese") == "bose"
        assert normalize("Ärger") == normalize("Aerger") == "arger"

    def test_synonym_keys_are_normalized(self):
        assert SYNONYMS
        for phrase in SYNONYMS:
            assert normalize(phrase) == phrase


class TestSynonyms:
    @pytest.mark.parametrize(
        "query", ["passport", "Passport renewal", "паспорт", "Reisepass"]
    )
    def test_passport(self, query):
        assert ids(query)[0] == PASSPORT

    @pytest.mark.parametrize("query", ["ID card", "Ausweis", "удостоверение личности"])
    def test_id_card(self, query):
        assert ids(query)[0] == ID_CARD

    @pytest.mark.parametrize(
        "query", ["Anmeldung", "address registration", "регистрация", "прописка"]
    )
    def test_address_registration(self, query):
        assert ids(query)[0] == ANMELDUNG

    @pytest.mark.parametrize(
        "query", ["driving licence", "driver license", "водительские права", "права"]
    )
    def test_driving_licence(self, query):
        assert ids(query)[0] == LICENCE

    @pytest.mark.parametrize("query", ["deregister car", "снять машину с учета"])
    def test_car_deregistration(self, query):
        assert ids(query)[0] == CAR_DEREG

    @pytest.mark.parametrize(
        "query", ["residence permit", "Aufenthaltstitel", "внж", "вид на жительство"]
    )
    def test_residence_permit_in_popular_order(self, query):
        found = ids(query)
        assert found[:2] == [URGENT_WORK, URGENT_STUDY]

    def test_more_matching_phrases_rank_higher(self):
        assert ids("student visa")[:2] == [URGENT_STUDY, URGENT_WORK]

    def test_students(self):
        assert ids("студент")[0] == URGENT_STUDY

    def test_card_pickup(self):
        assert ids("pick up residence card")[0] == EAT_PICKUP
        assert ids("получить карту внж")[0] == EAT_PICKUP

    def test_short_synonym_needs_whole_word(self):
        assert CAR_DEREG not in ids("id card")

    def test_targets_missing_from_catalog_are_skipped(self):
        services = [s for s in CATALOG_SERVICES if s["id"] != PASSPORT]
        assert PASSPORT not in ids("паспорт", services)


class TestNameSynonyms:
    """Synonyms for services outside the popular list point to words of their German name"""

    @pytest.mark.parametrize(
        "query", ["citizenship", "naturalisation", "naturalization", "гражданство"]
    )
    def test_citizenship(self, query):
        assert ids(query) == [EINBUERGERUNG]

    @pytest.mark.parametrize("query", ["parking permit", "парковка"])
    def test_resident_parking(self, query):
        assert ids(query)[0] == PARKING

    @pytest.mark.parametrize(
        "query", ["регистрация машины", "car registration", "register a car"]
    )
    def test_vehicle_registration_before_address_or_deregistration(self, query):
        vehicles = [
            {"id": 1064308, "name": "Erneute Anmeldung eines Fahrzeugs"},
            {
                "id": 1063425,
                "name": "Anmeldung fabrikneues Fahrzeug oder Tageszulassung",
            },
        ]
        found = ids(query, CATALOG_SERVICES + vehicles)
        assert set(found[:2]) == {1064308, 1063425}


class TestTypos:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("pasport", PASSPORT),
            ("паспрот", PASSPORT),
            ("anmeldnug", ANMELDUNG),
            ("Einbürgerunk", EINBUERGERUNG),
        ],
    )
    def test_one_typo_in_a_long_word(self, query, expected):
        assert ids(query)[0] == expected

    def test_short_words_are_not_corrected(self):
        assert ids("cer") == []

    def test_exact_matches_are_not_widened(self):
        assert ids("reisepass") == [PASSPORT]

    def test_corrections_follow_a_replaced_catalog(self):
        hunde = [{"id": 1, "name": "Hundesteuer"}]
        assert search_services("hundestuer", CATALOG_SERVICES) == []
        assert search_services("hundestuer", hunde) == hunde
        assert search_services("hundestuer", CATALOG_SERVICES) == []

    @pytest.mark.parametrize(
        ("query", "found"),
        [
            ("anmedlung", True),  # swap
            ("anmeldunk", True),  # substitution
            ("anmeldunng", True),  # insertion
            ("anmldung", True),  # deletion
            ("anmeldungens", True),  # starts with a word one typo away
            ("anmdelunk", False),
            ("amneldunk", False),
        ],
    )
    def test_one_typo_kinds(self, query, found):
        services = [{"id": 1, "name": "Abmeldung Anmeldung"}]
        assert (search_services(query, services) == services) is found


class TestNameMatching:
    @pytest.mark.parametrize("query", ["führerschein", "fuehrerschein", "fuhrerschein"])
    def test_umlaut_variants_find_the_same_service(self, query):
        assert ids(query) == [LICENCE]

    def test_every_token_must_match(self):
        assert ids("fahrzeug abmelden") == [CAR_DEREG]
        assert ids("fahrzeug einbürgerung") == []

    def test_one_char_tokens_are_ignored(self):
        assert ids("fahrzeug a") == [CAR_DEREG]

    def test_nothing_found(self):
        assert ids("xyzzy") == []

    @pytest.mark.parametrize("query", ["", " ", "a", "ä", "!"])
    def test_query_shorter_than_two_chars(self, query):
        assert ids(query) == []

    def test_limit(self):
        services = [{"id": i, "name": f"Amt Nummer {i}"} for i in range(1, 21)]
        assert len(ids("amt", services)) == 8
        assert len(ids("amt", services, limit=3)) == 3

    def test_long_query_is_truncated_to_60_chars(self):
        assert ids("x" * 59 + " reisepass") == []
        assert ids("x" * 49 + " reisepass") == [PASSPORT]


class TestRanking:
    def test_synonym_hits_come_first(self):
        found = ids("anmeldung")
        assert found[0] == ANMELDUNG
        assert GEWERBE in found

    def test_popular_before_other_name_matches(self):
        services = [
            {"id": 1, "name": "Kinderpass beantragen"},
            {"id": ID_CARD, "name": "Personalausweis beantragen"},
        ]
        assert ids("beantragen", services) == [ID_CARD, 1]

    def test_names_starting_with_first_token_then_shorter(self):
        services = [
            {"id": 1, "name": "Neue Parkerlaubnis für Anwohner"},
            {"id": 2, "name": "Parkerlaubnis lang"},
            {"id": 3, "name": "Parkerlaubnis"},
        ]
        assert ids("parkerlaubnis", services) == [3, 2, 1]

    def test_popular_ids_cover_every_synonym_target(self):
        for targets in SYNONYMS.values():
            assert set(targets) <= set(POPULAR_SERVICE_IDS)
