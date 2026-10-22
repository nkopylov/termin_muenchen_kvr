# ABOUTME: Service search over German service names plus hand-kept English/Russian synonyms.
# ABOUTME: Pure functions: normalization, synonym lookup and ranking.

import re

from src.watches.labels import POPULAR_SERVICE_IDS

MAX_QUERY_CHARS = 60
MIN_TOKEN_CHARS = 2
# Synonym words shorter than this must match a whole query word ("car" must not match "card")
MIN_PREFIX_CHARS = 4

_URGENT_WORK = 10339028
_URGENT_STUDY = 10339027
_EAT_PICKUP = 10502137
_ANMELDUNG = 1063475
_ID_CARD = 1063441
_PASSPORT = 1063453
_LICENCE = 1071896
_CAR_DEREG = 1064305
_RESIDENCE = (_URGENT_WORK, _URGENT_STUDY)

# Phrase -> services. A phrase matches when each of its words equals a query word or,
# from MIN_PREFIX_CHARS letters on, starts one (Russian word endings vary).
_PHRASES: dict[str, tuple[int, ...]] = {
    # residence permit (Ausländerbehörde)
    "residence permit": _RESIDENCE,
    "work permit": (_URGENT_WORK,),
    "visa": _RESIDENCE,
    "blue card": (_URGENT_WORK,),
    "aufenthaltstitel": _RESIDENCE,
    "aufenthaltserlaubnis": _RESIDENCE,
    "blaue karte": (_URGENT_WORK,),
    "ausländerbehörde": _RESIDENCE,
    "abh": _RESIDENCE,
    "внж": (_URGENT_WORK, _URGENT_STUDY, _EAT_PICKUP),
    "вид на жительств": _RESIDENCE,
    "виза": _RESIDENCE,
    "голуб карт": (_URGENT_WORK,),
    "блю карт": (_URGENT_WORK,),
    "student": (_URGENT_STUDY,),
    "studium": (_URGENT_STUDY,),
    "студент": (_URGENT_STUDY,),
    "учеб": (_URGENT_STUDY,),
    # residence card pickup
    "pick up": (_EAT_PICKUP,),
    "pickup": (_EAT_PICKUP,),
    "collect": (_EAT_PICKUP,),
    "residence card": (_EAT_PICKUP,),
    "eat": (_EAT_PICKUP,),
    "abholung": (_EAT_PICKUP,),
    "карт внж": (_EAT_PICKUP,),
    "получ": (_EAT_PICKUP,),
    "забра": (_EAT_PICKUP,),
    # address registration
    "anmeldung": (_ANMELDUNG,),
    "wohnsitz": (_ANMELDUNG,),
    "ummeldung": (_ANMELDUNG,),
    "registration": (_ANMELDUNG,),
    "register address": (_ANMELDUNG,),
    "address": (_ANMELDUNG,),
    "регистрац": (_ANMELDUNG,),
    "прописк": (_ANMELDUNG,),
    "адрес": (_ANMELDUNG,),
    # ID card
    "id card": (_ID_CARD,),
    "identity card": (_ID_CARD,),
    "ausweis": (_ID_CARD,),
    "personalausweis": (_ID_CARD,),
    "удостоверение личности": (_ID_CARD,),
    "айди": (_ID_CARD,),
    "id карт": (_ID_CARD,),
    # passport
    "passport": (_PASSPORT,),
    "reisepass": (_PASSPORT,),
    "паспорт": (_PASSPORT,),
    "загранпаспорт": (_PASSPORT,),
    # driving licence
    "driving licence": (_LICENCE,),
    "driving license": (_LICENCE,),
    "driver license": (_LICENCE,),
    "drivers license": (_LICENCE,),
    "licence": (_LICENCE,),
    "license": (_LICENCE,),
    "führerschein": (_LICENCE,),
    "водительск": (_LICENCE,),
    "прав": (_LICENCE,),
    # car deregistration
    "car": (_CAR_DEREG,),
    "deregist": (_CAR_DEREG,),
    "abmelden": (_CAR_DEREG,),
    "машин": (_CAR_DEREG,),
    "автомоб": (_CAR_DEREG,),
}

_UMLAUTS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "ё": "е"})
_DIGRAPHS = (("ae", "a"), ("oe", "o"), ("ue", "u"))
_SEPARATORS = re.compile(r"[\W_]+")


def normalize(text: str) -> str:
    """Casefolded words without umlauts or their ae/oe/ue spellings, joined by single spaces."""
    text = text.casefold().translate(_UMLAUTS)
    for digraph, letter in _DIGRAPHS:
        text = text.replace(digraph, letter)
    return " ".join(word for word in _SEPARATORS.split(text) if word)


SYNONYMS: dict[str, tuple[int, ...]] = {
    normalize(phrase): service_ids for phrase, service_ids in _PHRASES.items()
}


def _word_matches(phrase_word: str, query_words: list[str]) -> bool:
    if len(phrase_word) < MIN_PREFIX_CHARS:
        return phrase_word in query_words
    return any(word.startswith(phrase_word) for word in query_words)


def _synonym_hits(query_words: list[str]) -> dict[int, int]:
    """Service id -> number of synonym phrases in the query that point to it."""
    hits: dict[int, int] = {}
    for phrase, service_ids in SYNONYMS.items():
        if all(_word_matches(word, query_words) for word in phrase.split()):
            for service_id in service_ids:
                hits[service_id] = hits.get(service_id, 0) + 1
    return hits


def _popular_rank(service_id: int) -> int:
    if service_id in POPULAR_SERVICE_IDS:
        return POPULAR_SERVICE_IDS.index(service_id)
    return len(POPULAR_SERVICE_IDS)


def search_services(query: str, services: list[dict], limit: int = 8) -> list[dict]:
    """Services matching the query, best first; [] for queries without a 2-letter word."""
    query_words = normalize(query[:MAX_QUERY_CHARS]).split()
    tokens = [word for word in query_words if len(word) >= MIN_TOKEN_CHARS]
    if not tokens:
        return []

    hits = _synonym_hits(query_words)
    ranked = []
    for service in services:
        name = normalize(service["name"])
        synonym_hits = hits.get(service["id"], 0)
        if not synonym_hits and not all(token in name for token in tokens):
            continue
        key = (
            -synonym_hits,
            _popular_rank(service["id"]),
            not name.startswith(tokens[0]),
            len(name),
            name,
        )
        ranked.append((key, service))
    ranked.sort(key=lambda item: item[0])
    return [service for _, service in ranked[:limit]]
