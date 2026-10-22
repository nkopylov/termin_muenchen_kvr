# ABOUTME: Service search over German service names plus hand-kept English/Russian synonyms.
# ABOUTME: Pure functions: normalization, synonym lookup and ranking.

SYNONYMS: dict[str, tuple[int, ...]] = {}


def normalize(text: str) -> str:
    raise NotImplementedError


def search_services(query: str, services: list[dict], limit: int = 8) -> list[dict]:
    raise NotImplementedError
