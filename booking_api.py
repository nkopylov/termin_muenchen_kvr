"""
Booking API module for Munich appointment system
Handles the 3-step booking process: reserve -> update -> preconfirm
"""
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def reserve_appointment(timestamp: int, office_id: int, service_id: int, captcha_token: str) -> Optional[Dict[str, Any]]:
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
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/reserve-appointment/"

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Origin": "https://stadt.muenchen.de",
        "Referer": "https://stadt.muenchen.de/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
        "Priority": "u=3, i"
    }

    data = {
        "timestamp": timestamp,
        "serviceCount": [1],
        "officeId": office_id,
        "serviceId": [service_id],
        "captchaToken": captcha_token
    }

    try:
        logger.info(f"Reserving appointment: timestamp={timestamp}, office={office_id}, service={service_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get('processId') and result.get('authKey'):
            logger.info(f"Appointment reserved successfully: processId={result['processId']}, authKey={result['authKey']}")
            return result
        else:
            logger.error(f"Reservation failed: missing processId or authKey in response: {result}")
            return None

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error during reservation: {e.response.status_code}")
        try:
            error_data = e.response.json()
            logger.error(f"Error details: {error_data}")
        except:
            logger.error(f"Response text: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during reservation: {e}")
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
    custom_textfield2: str = ""
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
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/update-appointment/"

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Origin": "https://stadt.muenchen.de",
        "Referer": "https://stadt.muenchen.de/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
        "Priority": "u=3, i"
    }

    data = {
        "processId": process_id,
        "timestamp": timestamp,
        "authKey": auth_key,
        "familyName": family_name,
        "customTextfield": custom_textfield,
        "customTextfield2": custom_textfield2,
        "email": email,
        "telephone": telephone,
        "officeName": scope.get('provider', {}).get('name', ''),
        "officeId": office_id,
        "scope": scope,
        "subRequestCounts": [],
        "serviceId": service_id,
        "serviceName": "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige",
        "serviceCount": 1,
        "status": "reserved",
        "captchaToken": "",
        "slotCount": 1
    }

    try:
        logger.info(f"Updating appointment {process_id} with user info: name={family_name}, email={email}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Appointment updated successfully: processId={process_id}")
        return result

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error during update: {e.response.status_code}")
        try:
            error_data = e.response.json()
            logger.error(f"Error details: {error_data}")
        except:
            logger.error(f"Response text: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during update: {e}")
        return None


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
    custom_textfield2: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Step 3: Preconfirm appointment (final step before email confirmation)

    Args:
        Same as update_appointment

    Returns:
        Preconfirmed appointment data or None if failed
    """
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/preconfirm-appointment/"

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Origin": "https://stadt.muenchen.de",
        "Referer": "https://stadt.muenchen.de/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
        "Priority": "u=3, i"
    }

    data = {
        "processId": process_id,
        "timestamp": timestamp,
        "authKey": auth_key,
        "familyName": family_name,
        "customTextfield": custom_textfield,
        "customTextfield2": custom_textfield2,
        "email": email,
        "telephone": telephone,
        "officeName": scope.get('provider', {}).get('name', ''),
        "officeId": office_id,
        "scope": scope,
        "subRequestCounts": [],
        "serviceId": service_id,
        "serviceName": "Notfall-Hilfe Aufenthaltstitel – Beschäftigte, Angehörige",
        "serviceCount": 1,
        "status": "preconfirmed",
        "captchaToken": "",
        "slotCount": 1
    }

    try:
        logger.info(f"Preconfirming appointment {process_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Appointment preconfirmed successfully: processId={process_id}")
        logger.info(f"User must now check email {email} to confirm the appointment")
        return result

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error during preconfirm: {e.response.status_code}")
        try:
            error_data = e.response.json()
            logger.error(f"Error details: {error_data}")
        except:
            logger.error(f"Response text: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during preconfirm: {e}")
        return None


def book_appointment_complete(
    timestamp: int,
    office_id: int,
    service_id: int,
    captcha_token: str,
    family_name: str,
    email: str,
    telephone: str = "",
    custom_textfield: str = "",
    custom_textfield2: str = ""
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

    process_id = reservation['processId']
    auth_key = reservation['authKey']
    timestamp_str = reservation['timestamp']
    scope = reservation['scope']

    # Step 2: Update with user info
    updated = update_appointment(
        process_id, auth_key, timestamp_str, family_name, email,
        office_id, service_id, scope, telephone, custom_textfield, custom_textfield2
    )
    if not updated:
        logger.error("Booking failed at update step")
        return None

    # Step 3: Preconfirm
    preconfirmed = preconfirm_appointment(
        process_id, auth_key, timestamp_str, family_name, email,
        office_id, service_id, scope, telephone, custom_textfield, custom_textfield2
    )
    if not preconfirmed:
        logger.error("Booking failed at preconfirm step")
        return None

    logger.info(f"Booking completed successfully! ProcessId={process_id}")
    return preconfirmed
