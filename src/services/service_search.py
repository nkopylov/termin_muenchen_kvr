# ABOUTME: Service search over German service names plus hand-kept English/Russian synonyms.
# ABOUTME: Pure functions: normalization, synonym lookup, ranking and a one-typo fallback.

import re

from src.watches.labels import POPULAR_SERVICE_IDS

MAX_QUERY_CHARS = 60
MIN_TOKEN_CHARS = 2
# Synonym words shorter than this must match a whole query word ("car" must not match "card")
MIN_PREFIX_CHARS = 4
# Query words this long may carry one typo when nothing matches as typed
MIN_TYPO_CHARS = 5

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

# Phrase -> words that must all be in the German name, for services outside the popular list
_NAME_PHRASES: dict[str, tuple[str, ...]] = {
    "citizenship": ("einbürgerung",),
    "naturalisation": ("einbürgerung",),
    "naturalization": ("einbürgerung",),
    "гражданств": ("einbürgerung",),
    "parking permit": ("bewohnerparkausweis",),
    "resident parking": ("bewohnerparkausweis",),
    "парковк": ("bewohnerparkausweis",),
    "car registration": ("anmeld", "fahrzeug"),
    "register car": ("anmeld", "fahrzeug"),
    "vehicle registration": ("anmeld", "fahrzeug"),
    "регистрац машин": ("anmeld", "fahrzeug"),
    "регистрац автомоб": ("anmeld", "fahrzeug"),
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
NAME_SYNONYMS: dict[str, tuple[str, ...]] = {
    normalize(phrase): tuple(normalize(word) for word in words)
    for phrase, words in _NAME_PHRASES.items()
}


def _word_matches(phrase_word: str, query_words: list[str]) -> bool:
    if len(phrase_word) < MIN_PREFIX_CHARS:
        return phrase_word in query_words
    return any(word.startswith(phrase_word) for word in query_words)


def _phrase_matches(phrase: str, query_words: list[str]) -> bool:
    return all(_word_matches(word, query_words) for word in phrase.split())


def _synonym_hits(query_words: list[str]) -> dict[int, int]:
    """Service id -> weight of the synonym phrases in the query that point to it (a
    phrase weighs its word count, so "регистрация машины" beats "регистрация" alone)."""
    hits: dict[int, int] = {}
    for phrase, service_ids in SYNONYMS.items():
        if _phrase_matches(phrase, query_words):
            for service_id in service_ids:
                hits[service_id] = hits.get(service_id, 0) + len(phrase.split())
    return hits


def _name_synonym_hits(name: str, query_words: list[str]) -> int:
    return sum(
        len(phrase.split())
        for phrase, words in NAME_SYNONYMS.items()
        if all(word in name for word in words) and _phrase_matches(phrase, query_words)
    )


def _typo_distance(a: str, b: str) -> int:
    """Edit distance counting a swap of two neighbouring letters as one edit."""
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], prev2[j - 2] + 1)
        prev2, prev = prev, row
    return prev[-1]


def _vocabulary(services: list[dict]) -> set[str]:
    words = {word for phrase in (*SYNONYMS, *NAME_SYNONYMS) for word in phrase.split()}
    for service in services:
        words.update(normalize(service["name"]).split())
    return {word for word in words if len(word) >= MIN_TYPO_CHARS}


def _corrected(word: str, vocabulary: set[str]) -> str:
    """The vocabulary word one typo away from `word` (or from its start, for stems)."""
    if len(word) < MIN_TYPO_CHARS or word in vocabulary:
        return word
    for candidate in sorted(vocabulary):
        if _typo_distance(word, candidate) <= 1:
            return candidate
        if len(word) > len(candidate) and (
            _typo_distance(word[: len(candidate)], candidate) <= 1
        ):
            return candidate
    return word


def _popular_rank(service_id: int) -> int:
    if service_id in POPULAR_SERVICE_IDS:
        return POPULAR_SERVICE_IDS.index(service_id)
    return len(POPULAR_SERVICE_IDS)


def search_services(query: str, services: list[dict], limit: int = 8) -> list[dict]:
    """Services matching the query, best first; [] for queries without a 2-letter word.
    When nothing matches, long words are corrected by one typo and the search repeated."""
    query_words = normalize(query[:MAX_QUERY_CHARS]).split()
    found = _search(query_words, services, limit)
    if found:
        return found
    vocabulary = _vocabulary(services)
    corrected = [_corrected(word, vocabulary) for word in query_words]
    if corrected == query_words:
        return []
    return _search(corrected, services, limit)


def _search(query_words: list[str], services: list[dict], limit: int) -> list[dict]:
    tokens = [word for word in query_words if len(word) >= MIN_TOKEN_CHARS]
    if not tokens:
        return []

    hits = _synonym_hits(query_words)
    ranked = []
    for service in services:
        name = normalize(service["name"])
        synonym_hits = hits.get(service["id"], 0) + _name_synonym_hits(
            name, query_words
        )
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
