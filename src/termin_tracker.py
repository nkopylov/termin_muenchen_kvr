import base64
import hashlib
import json
import logging
import struct
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)

# Thread pool for CPU-intensive CAPTCHA solving
_captcha_executor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="captcha-solver"
)


def get_captcha_challenge():
    """
    Get a captcha challenge from the server.
    Returns the challenge data dict.
    """
    api_client = get_api_client()
    logger.info("Requesting captcha challenge from server...")

    challenge_data = api_client.get("captcha-challenge/")
    if challenge_data:
        logger.info(
            f"Captcha challenge received: cost={challenge_data.get('parameters', {}).get('cost', 'unknown')}"
        )
    else:
        logger.error("Failed to get captcha challenge")

    return challenge_data


HASH_ALGORITHMS = {"SHA-256": "sha256", "SHA-384": "sha384", "SHA-512": "sha512"}


def solve_captcha_challenge(challenge_data):
    """
    Solve the ALTCHA proof-of-work challenge.
    challenge_data: dict with "parameters" (algorithm, nonce, salt, cost, keyLength, keyPrefix) and "signature"
    Returns the solution dict with counter, derivedKey and time taken in ms.
    """
    parameters = challenge_data.get("parameters", {})
    algorithm = parameters.get("algorithm")
    hash_name = HASH_ALGORITHMS.get(algorithm)
    if hash_name is None:
        logger.error(f"Unsupported captcha algorithm: {algorithm}")
        return None

    salt = bytes.fromhex(parameters["salt"])
    nonce = bytes.fromhex(parameters["nonce"])
    key_prefix = parameters["keyPrefix"].lower()
    key_length = parameters.get("keyLength") or 32
    cost = max(1, parameters.get("cost", 1))

    logger.info(
        f"Solving captcha challenge (algorithm={algorithm}, cost={cost}, keyPrefix={key_prefix})..."
    )
    start_time = time.perf_counter()

    for counter in range(2**32):
        # Key = hash applied `cost` times to salt + nonce + big-endian uint32 counter
        derived_key = salt + nonce + struct.pack(">I", counter)
        for _ in range(cost):
            derived_key = hashlib.new(hash_name, derived_key).digest()
        derived_key_hex = derived_key[:key_length].hex()

        if derived_key_hex.startswith(key_prefix):
            took_ms = round((time.perf_counter() - start_time) * 1000, 1)
            logger.info(f"Captcha solved! Found counter: {counter} in {took_ms}ms")
            return {
                "counter": counter,
                "derivedKey": derived_key_hex,
                "time": took_ms,
            }

    logger.error("Failed to solve captcha: counter space exhausted")
    return None


def build_captcha_payload(challenge_data, solution):
    """
    Encode the challenge and its solution as the base64 JSON payload expected by captcha-verify.
    """
    payload = {
        "challenge": {
            "parameters": challenge_data["parameters"],
            "signature": challenge_data["signature"],
        },
        "solution": solution,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def verify_captcha_solution(challenge_data, solution):
    """
    Submit the captcha solution to get a JWT token.
    challenge_data: the challenge the solution was computed for
    solution: dict with the proof-of-work solution
    Returns the JWT token string.
    """
    api_client = get_api_client()

    data = {"payload": build_captcha_payload(challenge_data, solution)}

    logger.info("Verifying captcha solution with server...")
    result = api_client.post("captcha-verify/", data)

    if (
        result
        and result.get("meta", {}).get("success")
        and result.get("data", {}).get("valid")
    ):
        token = result.get("token")
        logger.info(f"Captcha token obtained successfully: {token[:50]}...")
        return token
    else:
        logger.error(f"Captcha verification failed: {result}")
        return None


async def get_fresh_captcha_token():
    """
    Complete captcha flow: get challenge, solve it, verify solution, get token.
    Runs CPU-intensive CAPTCHA solving in a thread pool to avoid blocking the event loop.
    Returns the JWT token string.
    """
    logger.info("Starting captcha token acquisition flow (async)...")

    # Step 1: Get challenge (I/O bound, quick)
    loop = asyncio.get_event_loop()
    challenge = await loop.run_in_executor(_captcha_executor, get_captcha_challenge)

    if not challenge:
        logger.error("Captcha flow failed: could not get challenge")
        return None

    # Step 2: Solve the challenge (CPU-intensive, run in thread)
    logger.info("Solving captcha in background thread...")
    solution = await loop.run_in_executor(
        _captcha_executor, solve_captcha_challenge, challenge
    )

    if not solution:
        logger.error("Captcha flow failed: could not solve challenge")
        return None

    # Step 3: Verify solution and get token (I/O bound, quick)
    token = await loop.run_in_executor(
        _captcha_executor, verify_captcha_solution, challenge, solution
    )

    if token:
        logger.info("Captcha token acquisition flow completed successfully")
    else:
        logger.error("Captcha flow failed: could not verify solution")
    return token


def get_available_calendar(
    start_date, end_date, office_id, service_id, captcha_token, slots_date=None
):
    """
    Query the available-calendar endpoint.
    The server returns appointment slots for one day only: slots_date, or the first bookable day if omitted.
    """
    api_client = get_api_client()

    params = {
        "startDate": start_date,
        "endDate": end_date,
        "officeIds": office_id,
        "serviceIds": service_id,
        "serviceCounts": "1",
        "captchaToken": captcha_token,
    }
    if slots_date:
        params["slotsStartDate"] = slots_date
        params["slotsEndDate"] = slots_date

    return api_client.get("available-calendar/", params=params)


def get_available_slots(date, office_id, service_id, captcha_token):
    """
    Get available time slots for a specific date.

    date: e.g. '2025-10-13'
    office_id: e.g. '10461' (can be comma-separated for multiple offices)
    service_id: e.g. '10339028'
    captcha_token: JWT token from the website (required for Ausländerbehörde services)

    Returns: {
        "date": "2025-10-13",
        "providerIDs": "10461",
        "offices": [
            {
                "officeId": "10461",
                "appointments": [1760340600, 1760340900, ...]  # Unix timestamps
            }
        ]
    }
    or None if the request failed.
    """
    logger.debug(
        f"Fetching slots for {date} (office={office_id}, service={service_id})"
    )
    data = get_available_calendar(
        date, date, office_id, service_id, captcha_token, slots_date=date
    )
    if data is None:
        return None

    day = next((d for d in data.get("availableDays", []) if d["date"] == date), None)
    if day is None:
        return {"date": date, "providerIDs": "", "offices": []}

    # Count total appointments across all offices
    total_appointments = sum(
        len(office.get("appointments", [])) for office in day.get("offices", [])
    )
    logger.debug(f"Successfully fetched {total_appointments} slots for {date}")
    return day


def get_available_days(
    start_date, end_date, captcha_token, office_id="10461", service_id="10339028"
):
    """
    Check available days in a date range.
    start_date: e.g. '2025-10-02'
    end_date: e.g. '2026-04-02'
    captcha_token: JWT token from the website
    Returns the calendar dict whose "availableDays" lists {"date", "providerIDs", "offices"} entries.
    """
    logger.info(
        f"Checking available days: {start_date} to {end_date} (office={office_id}, service={service_id})"
    )
    data = get_available_calendar(
        start_date, end_date, office_id, service_id, captcha_token
    )

    if data:
        logger.info(f"API response received: {data}")
    else:
        logger.error("Request failed while checking available days")

    return data
