"""
Service catalog manager for Munich appointment services.
Fetches and caches service categories and information.
"""

import logging
from typing import Dict, List, Optional
from collections import defaultdict

from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)

# Category definitions
CATEGORY_KEYWORDS = {
    "Ausländerbehörde 🌍": [
        "Aufenthaltstitel",
        "Duldung",
        "eAT",
        "Verpflichtungserklärung",
    ],
    "Ausweis & Pass 🆔": ["Personalausweis", "Reisepass", "eID"],
    "Fahrzeug 🚗": ["Fahrzeug", "KfZ", "Kfz", "Kennzeichen", "Zulassung"],
    "Führerschein 🪪": [
        "Führerschein",
        "Fahrerlaubnis",
        "Fahrerqualifizierung",
        "Personenbeförderungsschein",
    ],
    "Wohnsitz 🏠": ["Wohnsitz", "Melde", "Adress"],
    "Gewerbe 💼": [
        "Gewerbe",
        "Taxi",
        "Mietwagen",
        "Güter",
        "Bewachung",
        "Pfandleiher",
        "Versteigerung",
    ],
    "Familie 👨\u200d👩\u200d👧": [
        "Eheschließung",
        "Unterhaltsvorschuss",
        "Vaterschaft",
        "Elternberatung",
    ],
    "Rente & Soziales 🏥": ["Rente", "Versicherung", "BAföG", "Sozial"],
    "Parken 🅿️": ["Park", "Bewohner"],
    "Sonstiges 📋": [],
}

# Cache for services
_services_cache = None
_offices_cache = None
_full_payload_cache = None


def fetch_services() -> Optional[List[Dict]]:
    """Fetch all available services from API"""
    api_client = get_api_client()
    data = api_client.get("services")

    if data:
        services = data.get("services", [])
        logger.info(f"Fetched {len(services)} services from API")
        return services
    else:
        logger.error("Failed to fetch services")
        return None


def fetch_offices() -> Optional[List[Dict]]:
    """Fetch all available offices from API"""
    api_client = get_api_client()
    data = api_client.get("offices")

    if data:
        offices = data.get("offices", [])
        logger.info(f"Fetched {len(offices)} offices from API")
        return offices
    else:
        logger.error("Failed to fetch offices")
        return None


def fetch_full_payload() -> Optional[Dict]:
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


def get_services() -> List[Dict]:
    """Get services (cached)"""
    global _services_cache
    if _services_cache is None:
        _services_cache = fetch_services()
    return _services_cache or []


def get_offices() -> List[Dict]:
    """Get offices (cached)"""
    global _offices_cache
    if _offices_cache is None:
        _offices_cache = fetch_offices()
    return _offices_cache or []


def get_full_payload() -> Dict:
    """Get full payload (cached)"""
    global _full_payload_cache
    if _full_payload_cache is None:
        _full_payload_cache = fetch_full_payload()
    return _full_payload_cache or {"offices": [], "services": [], "relations": []}


def categorize_services() -> Dict[str, List[Dict]]:
    """Organize services into categories"""
    services = get_services()
    categories = defaultdict(list)

    for service in services:
        name = service["name"]
        sid = service["id"]
        categorized = False

        for category, keywords in CATEGORY_KEYWORDS.items():
            if category == "Sonstiges 📋":
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
            categories["Sonstiges 📋"].append(
                {"id": sid, "name": name, "maxQuantity": service.get("maxQuantity", 1)}
            )

    # Sort services within each category
    for category in categories:
        categories[category].sort(key=lambda x: x["name"])

    return dict(categories)


def get_service_info(service_id: int) -> Optional[Dict]:
    """Get detailed information for a specific service"""
    services = get_services()
    for service in services:
        if service["id"] == service_id:
            return service
    return None


def get_office_info(office_id: int) -> Optional[Dict]:
    """Get detailed information for a specific office"""
    offices = get_offices()
    for office in offices:
        if office["id"] == office_id:
            return office
    return None


def get_category_for_service(service_id: int) -> Optional[str]:
    """Find which category a service belongs to"""
    categories = categorize_services()
    for category, services in categories.items():
        for service in services:
            if service["id"] == service_id:
                return category
    return None


def get_offices_for_service(service_id: int) -> List[Dict]:
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


def get_default_office_for_service(service_id: int) -> Optional[int]:
    """
    Get the default/preferred office ID for a service.
    Prioritizes Ausländerbehörde office 10461 (Notfalltermine) for residence permit services.
    Returns None if no suitable office is found.
    """
    offices = get_offices_for_service(service_id)
    if not offices:
        logger.warning(f"No offices found for service {service_id}")
        return None

    # Priority list for Ausländerbehörde services
    priority_offices = [10461, 10187259, 10446, 10454, 10455]

    # Check if this is an Ausländerbehörde service
    service_info = get_service_info(service_id)
    if service_info:
        service_name = service_info.get("name", "").lower()
        is_foreigners_office = any(
            keyword in service_name
            for keyword in ["aufenthalt", "notfall", "duldung", "visum", "ausländer"]
        )

        if is_foreigners_office:
            # Try to find priority offices
            for priority_id in priority_offices:
                for office in offices:
                    if office["id"] == priority_id:
                        logger.info(
                            f"Selected priority office {priority_id} for service {service_id}"
                        )
                        return priority_id

    # Default: return first office with valid scope
    for office in offices:
        if office.get("scope") and office["scope"].get("id", 0) > 0:
            office_id = office["id"]
            logger.info(f"Selected default office {office_id} for service {service_id}")
            return office_id

    # Fallback: return first office
    office_id = offices[0]["id"]
    logger.info(f"Selected fallback office {office_id} for service {service_id}")
    return office_id


# Refresh cache on module load
def refresh_cache():
    """Force refresh of cached data"""
    global _services_cache, _offices_cache, _full_payload_cache
    _services_cache = None
    _offices_cache = None
    _full_payload_cache = None
    get_services()
    get_offices()
    get_full_payload()
    logger.info("Service cache refreshed")
