"""
Booking API module for Munich appointment system
Handles the 3-step booking process: reserve -> update -> preconfirm
"""

import logging
from typing import Dict, Any, Optional

from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)


def reserve_appointment(
    timestamp: int, office_id: int, service_id: int, captcha_token: str
) -> Optional[Dict[str, Any]]:
    """
    Step 1: Reserve an appointment slot

    Args:
        timestamp: Unix timestamp of the appointment slot
        office_id: Office ID (e.g., 10461)
        service_id: Service ID (e.g., 10339028)
        captcha_token: Valid captcha JWT token

    Returns:
        Response dict with processId, authKey, timestamp, scope, etc.
        None if reservation failed
    """
    api_client = get_api_client()

    data = {
        "timestamp": timestamp,
        "serviceCount": [1],
        "officeId": office_id,
        "serviceId": [service_id],
        "captchaToken": captcha_token,
    }

    logger.info(
        f"Reserving appointment: timestamp={timestamp}, office={office_id}, service={service_id}"
    )
    result = api_client.post("reserve-appointment/", data)

    if result and result.get("processId") and result.get("authKey"):
        logger.info(
            f"Appointment reserved successfully: processId={result['processId']}, authKey={result['authKey']}"
        )
        return result
    else:
        logger.error(
            f"Reservation failed: missing processId or authKey in response: {result}"
        )
        return None


def update_appointment(
    process_id: int,
    auth_key: str,
    timestamp: str,
    family_name: str,
    email: str,
    office_id: int,
    service_id: int,
    scope: Dict[str, Any],
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Step 2: Update appointment with user information

    Args:
        process_id: Process ID from reserve step
        auth_key: Auth key from reserve step
        timestamp: Timestamp string from reserve step
        family_name: User's full name
        email: User's email address
        office_id: Office ID
        service_id: Service ID
        scope: Scope object from reserve step
        telephone: Optional phone number
        custom_textfield: Optional custom field 1
        custom_textfield2: Optional custom field 2

    Returns:
        Updated appointment data or None if failed
    """
    api_client = get_api_client()

    data = {
        "processId": process_id,
        "timestamp": timestamp,
        "authKey": auth_key,
        "familyName": family_name,
        "customTextfield": custom_textfield,
        "customTextfield2": custom_textfield2,
        "email": email,
        "telephone": telephone,
        "officeName": scope.get("provider", {}).get("name", ""),
        "officeId": office_id,
        "scope": scope,
        "subRequestCounts": [],
        "serviceId": service_id,
        "serviceName": "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige",
        "serviceCount": 1,
        "status": "reserved",
        "captchaToken": "",
        "slotCount": 1,
    }

    logger.info(
        f"Updating appointment {process_id} with user info: name={family_name}, email={email}"
    )
    result = api_client.post("update-appointment/", data)

    if result:
        logger.info(f"Appointment updated successfully: processId={process_id}")

    return result


def preconfirm_appointment(
    process_id: int,
    auth_key: str,
    timestamp: str,
    family_name: str,
    email: str,
    office_id: int,
    service_id: int,
    scope: Dict[str, Any],
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Step 3: Preconfirm appointment (final step before email confirmation)

    Args:
        Same as update_appointment

    Returns:
        Preconfirmed appointment data or None if failed
    """
    api_client = get_api_client()

    data = {
        "processId": process_id,
        "timestamp": timestamp,
        "authKey": auth_key,
        "familyName": family_name,
        "customTextfield": custom_textfield,
        "customTextfield2": custom_textfield2,
        "email": email,
        "telephone": telephone,
        "officeName": scope.get("provider", {}).get("name", ""),
        "officeId": office_id,
        "scope": scope,
        "subRequestCounts": [],
        "serviceId": service_id,
        "serviceName": "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige",
        "serviceCount": 1,
        "status": "preconfirmed",
        "captchaToken": "",
        "slotCount": 1,
    }

    logger.info(f"Preconfirming appointment {process_id}")
    result = api_client.post("preconfirm-appointment/", data)

    if result:
        logger.info(f"Appointment preconfirmed successfully: processId={process_id}")
        logger.info(f"User must now check email {email} to confirm the appointment")

    return result


def book_appointment_complete(
    timestamp: int,
    office_id: int,
    service_id: int,
    captcha_token: str,
    family_name: str,
    email: str,
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Complete booking flow: reserve -> update -> preconfirm

    Args:
        timestamp: Unix timestamp of the appointment slot
        office_id: Office ID
        service_id: Service ID
        captcha_token: Valid captcha JWT token
        family_name: User's full name
        email: User's email address
        telephone: Optional phone number
        custom_textfield: Optional custom field 1
        custom_textfield2: Optional custom field 2

    Returns:
        Final preconfirmed appointment data or None if any step failed
    """
    logger.info(f"Starting complete booking flow for {family_name} ({email})")

    # Step 1: Reserve
    reservation = reserve_appointment(timestamp, office_id, service_id, captcha_token)
    if not reservation:
        logger.error("Booking failed at reservation step")
        return None

    process_id = reservation["processId"]
    auth_key = reservation["authKey"]
    timestamp_str = reservation["timestamp"]
    scope = reservation["scope"]

    # Step 2: Update with user info
    updated = update_appointment(
        process_id,
        auth_key,
        timestamp_str,
        family_name,
        email,
        office_id,
        service_id,
        scope,
        telephone,
        custom_textfield,
        custom_textfield2,
    )
    if not updated:
        logger.error("Booking failed at update step")
        return None

    # Step 3: Preconfirm
    preconfirmed = preconfirm_appointment(
        process_id,
        auth_key,
        timestamp_str,
        family_name,
        email,
        office_id,
        service_id,
        scope,
        telephone,
        custom_textfield,
        custom_textfield2,
    )
    if not preconfirmed:
        logger.error("Booking failed at preconfirm step")
        return None

    logger.info(f"Booking completed successfully! ProcessId={process_id}")
    return preconfirmed
