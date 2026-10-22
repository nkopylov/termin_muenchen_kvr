"""
Service catalog manager for Munich appointment services.
Fetches and caches service categories and information.
"""

import functools
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import TypeVar

from src.i18n import t
from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)

R = TypeVar("R")

# Category definitions keyed by stable id; labels are i18n keys "categories.<id>"
OTHER_CATEGORY = "sonstiges"

CATEGORY_KEYWORDS = {
    "auslaenderbehoerde": [
        "Aufenthaltstitel",
        "Duldung",
        "eAT",
        "Verpflichtungserklärung",
    ],
    "ausweis": ["Personalausweis", "Reisepass", "eID"],
    "fahrzeug": ["Fahrzeug", "KfZ", "Kfz", "Kennzeichen", "Zulassung"],
    "fuehrerschein": [
        "Führerschein",
        "Fahrerlaubnis",
        "Fahrerqualifizierung",
        "Personenbeförderungsschein",
    ],
    "wohnsitz": ["Wohnsitz", "Melde", "Adress"],
    "gewerbe": [
        "Gewerbe",
        "Taxi",
        "Mietwagen",
        "Güter",
        "Bewachung",
        "Pfandleiher",
        "Versteigerung",
    ],
    "familie": [
        "Eheschließung",
        "Unterhaltsvorschuss",
        "Vaterschaft",
        "Elternberatung",
    ],
    "soziales": ["Rente", "Versicherung", "BAföG", "Sozial"],
    "parken": ["Park", "Bewohner"],
    OTHER_CATEGORY: [],
}

# Cache for services
_services_cache = None
_full_payload_cache = None


def fetch_full_payload() -> dict | None:
    """
    Fetch the complete offices-and-services payload.
    This contains offices, services, and relations arrays.
    The relations array is the authoritative source for service-to-office mappings.
    """
    api_client = get_api_client()
    data = api_client.get("offices-and-services/")

    if data:
        logger.info(
            f"Fetched full payload with {len(data.get('relations', []))} relations"
        )
        return data
    else:
        logger.error("Failed to fetch full payload")
        return None


def refresh_catalog() -> bool:
    """Re-fetch the catalog; caches are replaced only when the fetch returned services"""
    global _services_cache, _full_payload_cache
    payload = fetch_full_payload()
    if not payload or not payload.get("services"):
        logger.warning("Catalog refresh failed, keeping the cached catalog")
        return False
    _full_payload_cache = payload
    _services_cache = payload["services"]
    logger.info(f"Catalog refreshed: {len(_services_cache)} services")
    return True


def catalog_loaded() -> bool:
    return bool(_services_cache) and bool(get_full_payload().get("relations"))


def per_catalog(fn: Callable[..., R]) -> Callable[..., R]:
    """Memoizes fn by its positional arguments until the cached catalog is replaced.
    Results are shared between callers, so they must not be mutated."""
    memo: dict[tuple, R] = {}
    source: tuple = (None, None)

    @functools.wraps(fn)
    def wrapper(*args) -> R:
        nonlocal source
        current = (_full_payload_cache, _services_cache)
        if current[0] is not source[0] or current[1] is not source[1]:
            memo.clear()
            source = current
        if args not in memo:
            memo[args] = fn(*args)
        return memo[args]

    return wrapper


def get_services() -> list[dict]:
    """Cached services; empty until refresh_catalog has succeeded (never fetches, since
    callers run on the event loop)"""
    return _services_cache or []


def get_full_payload() -> dict:
    """Cached catalog; empty until refresh_catalog has succeeded (never fetches)"""
    return _full_payload_cache or {"offices": [], "services": [], "relations": []}


def categorize_services() -> dict[str, list[dict]]:
    """Organize services into categories, keyed by category id"""
    services = get_services()
    categories = defaultdict(list)

    for service in services:
        name = service["name"]
        sid = service["id"]
        categorized = False

        for category, keywords in CATEGORY_KEYWORDS.items():
            if category == OTHER_CATEGORY:
                continue
            for keyword in keywords:
                if keyword.lower() in name.lower():
                    categories[category].append(
                        {
                            "id": sid,
                            "name": name,
                            "maxQuantity": service.get("maxQuantity", 1),
                        }
                    )
                    categorized = True
                    break
            if categorized:
                break

        if not categorized:
            categories[OTHER_CATEGORY].append(
                {"id": sid, "name": name, "maxQuantity": service.get("maxQuantity", 1)}
            )

    # Sort services within each category
    for category in categories:
        categories[category].sort(key=lambda x: x["name"])

    return dict(categories)


def get_service_info(service_id: int) -> dict | None:
    """Get detailed information for a specific service"""
    services = get_services()
    for service in services:
        if service["id"] == service_id:
            return service
    return None


def get_category_for_service(service_id: int) -> str | None:
    """Find the id of the category a service belongs to"""
    categories = categorize_services()
    for category, services in categories.items():
        for service in services:
            if service["id"] == service_id:
                return category
    return None


def get_offices_for_service(service_id: int) -> list[dict]:
    """
    Get designated offices for a specific service from the relations array.
    This returns ONLY the offices that are designated for appointment booking,
    not all offices that technically support the service.

    Returns a list of office dictionaries with id, name, and scope information.
    """
    payload = get_full_payload()

    # Find matching relations for this service (only public ones)
    office_ids = [
        r["officeId"]
        for r in payload.get("relations", [])
        if r["serviceId"] == service_id and r.get("public", True)
    ]

    # Get office details for these IDs
    offices = [
        office for office in payload.get("offices", []) if office["id"] in office_ids
    ]

    logger.info(
        f"Service {service_id} has {len(offices)} designated office(s) from relations array"
    )
    return offices


def get_office_name(office_id: int, lang: str | None = None) -> str:
    """
    Get office name by ID. Returns 'Office {id}' if not found, or its
    translation in `lang` when a language is given.
    """
    if lang is None:
        fallback = f"Office {office_id}"
    else:
        fallback = t("watch.office_fallback", lang, office_id=office_id)
    payload = get_full_payload()
    for office in payload.get("offices", []):
        if office["id"] == office_id:
            return office.get("name", fallback)
    return fallback
