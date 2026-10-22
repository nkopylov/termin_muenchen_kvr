"""
Service catalog manager for Munich appointment services.
Fetches and caches service categories and information.
"""

import logging
from collections import defaultdict

from src.i18n import t
from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)

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


def fetch_services() -> list[dict] | None:
    """Fetch all available services from API"""
    services = get_full_payload().get("services", [])

    if services:
        logger.info(f"Fetched {len(services)} services from API")
        return services
    else:
        logger.error("Failed to fetch services")
        return None


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


def get_services() -> list[dict]:
    """Get services (cached)"""
    global _services_cache
    if _services_cache is None:
        _services_cache = fetch_services()
    return _services_cache or []


def get_full_payload() -> dict:
    """Get full payload (cached)"""
    global _full_payload_cache
    if _full_payload_cache is None:
        _full_payload_cache = fetch_full_payload()
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
        fallback = t("buttons.office_fallback", lang, office_id=office_id)
    payload = get_full_payload()
    for office in payload.get("offices", []):
        if office["id"] == office_id:
            return office.get("name", fallback)
    return fallback
