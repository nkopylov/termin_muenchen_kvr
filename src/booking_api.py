# ABOUTME: Booking calls to the city's appointment API: reserve, fill in contact details, preconfirm.
# ABOUTME: Reserving uses a fresh captcha token and retries once with a new one if the city rejects it.
"""
Booking API module for Munich appointment system
Handles the 3-step booking process: reserve -> update -> preconfirm
"""

import asyncio
import logging
from typing import Any

from src.munich_api_client import ApiResponse, get_api_client
from src.services import captcha_token as tokens

logger = logging.getLogger(__name__)

# A booking makes three calls; the token must outlive at least the reserve call
BOOKING_TOKEN_MIN_TTL = 60.0


def reserve_appointment(
    timestamp: int, office_id: int, service_id: int, captcha_token: str
) -> ApiResponse:
    """
    Step 1: Reserve an appointment slot

    Args:
        timestamp: Unix timestamp of the appointment slot
        office_id: Office ID (e.g., 10461)
        service_id: Service ID (e.g., 10339028)
        captcha_token: Valid captcha JWT token

    Returns:
        The API response; on success its data has processId, authKey, timestamp, scope, etc.
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
    return api_client.post_result("reserve-appointment/", data)


def _reservation(response: ApiResponse) -> dict[str, Any] | None:
    """The reservation in a reserve response, or None if the slot was not reserved"""
    result = response.data
    if response.ok and result.get("processId") and result.get("authKey"):
        logger.info(
            f"Appointment reserved successfully: processId={result['processId']}, authKey={result['authKey']}"
        )
        return result
    logger.error(
        f"Reservation failed: status={response.status}, errors={list(response.error_codes)}, response={result}"
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
    service_name: str,
    scope: dict[str, Any],
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> dict[str, Any] | None:
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
        service_name: Service name as in the city's catalog
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
        "serviceName": service_name,
        "serviceCount": 1,
        "status": "reserved",
        "captchaToken": "",
        "slotCount": 1,
    }

    logger.info(
        f"Updating appointment {process_id} with user info: name={family_name}, email={email}"
    )
    result = api_client.post_result("update-appointment/", data).data

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
    service_name: str,
    scope: dict[str, Any],
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> dict[str, Any] | None:
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
        "serviceName": service_name,
        "serviceCount": 1,
        "status": "preconfirmed",
        "captchaToken": "",
        "slotCount": 1,
    }

    logger.info(f"Preconfirming appointment {process_id}")
    result = api_client.post_result("preconfirm-appointment/", data).data

    if result:
        logger.info(f"Appointment preconfirmed successfully: processId={process_id}")
        logger.info(f"User must now check email {email} to confirm the appointment")

    return result


def complete_reservation(
    reservation: dict[str, Any],
    office_id: int,
    service_id: int,
    service_name: str,
    family_name: str,
    email: str,
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = "",
) -> dict[str, Any] | None:
    """
    Steps 2 and 3 for a reserved slot: update -> preconfirm

    Returns:
        Final preconfirmed appointment data or None if a step failed
    """
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
        service_name,
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
        service_name,
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


async def book_appointment(
    timestamp: int,
    office_id: int,
    service_id: int,
    service_name: str,
    family_name: str,
    email: str,
) -> dict[str, Any] | None:
    """
    Complete booking flow: reserve -> update -> preconfirm

    Reserves with a captcha token fetched right now; a token the city rejects is
    replaced and the reservation tried once more. HTTP calls run in a worker thread.

    Returns:
        Final preconfirmed appointment data or None if any step failed
    """
    logger.info(f"Starting complete booking flow for {family_name} ({email})")

    # Step 1: Reserve
    reservation = None
    for _attempt in range(2):
        token = await tokens.get_token(min_ttl=BOOKING_TOKEN_MIN_TTL)
        if token is None:
            logger.error("Booking failed: no captcha token")
            return None
        response = await asyncio.to_thread(
            reserve_appointment, timestamp, office_id, service_id, token
        )
        if tokens.is_token_error(response.error_codes):
            tokens.invalidate()
            continue
        reservation = _reservation(response)
        break
    if not reservation:
        logger.error("Booking failed at reservation step")
        return None

    return await asyncio.to_thread(
        complete_reservation,
        reservation,
        office_id,
        service_id,
        service_name,
        family_name,
        email,
    )
