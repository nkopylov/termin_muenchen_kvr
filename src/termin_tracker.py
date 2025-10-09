import base64
import hashlib
import json
import logging
import time

from src.munich_api_client import get_api_client

logger = logging.getLogger(__name__)


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
            f"Captcha challenge received: maxnumber={challenge_data.get('maxnumber', 'unknown')}"
        )
    else:
        logger.error("Failed to get captcha challenge")
        print("Failed to get captcha challenge")

    return challenge_data


def solve_captcha_challenge(challenge_data):
    """
    Solve the proof-of-work captcha challenge.
    challenge_data: dict with algorithm, challenge, maxnumber, salt, signature
    Returns the solution dict with number and time taken.
    """
    algorithm = challenge_data.get("algorithm", "SHA-256")
    challenge = challenge_data.get("challenge")
    maxnumber = challenge_data.get("maxnumber", 10000000)
    salt = challenge_data.get("salt")
    signature = challenge_data.get("signature")

    logger.info(
        f"Solving captcha challenge (algorithm={algorithm}, max {maxnumber} iterations)..."
    )
    print(f"Solving captcha challenge (max {maxnumber} iterations)...")
    start_time = time.time()

    for number in range(maxnumber):
        # Create the hash input: salt + number
        hash_input = f"{salt}{number}"
        # Calculate SHA-256 hash
        hash_result = hashlib.sha256(hash_input.encode()).hexdigest()

        # Check if hash matches the challenge
        if hash_result == challenge:
            took_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Captcha solved! Found number: {number} in {took_ms}ms")
            print(f"✓ Captcha solved! Found number: {number} (took {took_ms}ms)")
            return {
                "algorithm": algorithm,
                "challenge": challenge,
                "number": number,
                "salt": salt,
                "signature": signature,
                "took": took_ms,
            }

        # Progress indicator every 100k iterations
        if number > 0 and number % 100000 == 0:
            logger.debug(f"Captcha solving progress: {number:,} iterations")
            print(f"  Tried {number:,} numbers...")

    logger.error("Failed to solve captcha within maxnumber limit")
    print("Failed to solve captcha within maxnumber limit")
    return None


def verify_captcha_solution(solution):
    """
    Submit the captcha solution to get a JWT token.
    solution: dict with the proof-of-work solution
    Returns the JWT token string.
    """
    api_client = get_api_client()

    # Encode solution as base64 JSON payload
    solution_json = json.dumps(solution)
    payload = base64.b64encode(solution_json.encode()).decode()

    data = {"payload": payload}

    logger.info("Verifying captcha solution with server...")
    result = api_client.post("captcha-verify/", data)

    if (
        result
        and result.get("meta", {}).get("success")
        and result.get("data", {}).get("valid")
    ):
        token = result.get("token")
        logger.info(f"Captcha token obtained successfully: {token[:50]}...")
        print(f"✓ Got captcha token: {token[:50]}...")
        return token
    else:
        logger.error(f"Captcha verification failed: {result}")
        print(f"Captcha verification failed: {result}")
        return None


def get_fresh_captcha_token():
    """
    Complete captcha flow: get challenge, solve it, verify solution, get token.
    Returns the JWT token string.
    """
    logger.info("Starting captcha token acquisition flow...")

    # Step 1: Get challenge
    challenge = get_captcha_challenge()
    if not challenge:
        logger.error("Captcha flow failed: could not get challenge")
        return None

    # Step 2: Solve the challenge
    solution = solve_captcha_challenge(challenge)
    if not solution:
        logger.error("Captcha flow failed: could not solve challenge")
        return None

    # Step 3: Verify solution and get token
    token = verify_captcha_solution(solution)
    if token:
        logger.info("Captcha token acquisition flow completed successfully")
    else:
        logger.error("Captcha flow failed: could not verify solution")
    return token


def get_available_slots(date, office_id, service_id, captcha_token):
    """
    Get available time slots for a specific date using available-appointments-by-office endpoint.

    date: e.g. '2025-10-13'
    office_id: e.g. '10461' (can be comma-separated for multiple offices)
    service_id: e.g. '10339028'
    captcha_token: JWT token from the website (required for Ausländerbehörde services)

    Returns: {
        "offices": [
            {
                "officeId": 10461,
                "appointments": [1760340600, 1760340900, ...]  # Unix timestamps
            }
        ]
    }
    """
    api_client = get_api_client()

    params = {
        "date": date,
        "officeId": office_id,
        "serviceId": service_id,
        "serviceCount": "1",
        "captchaToken": captcha_token,
    }

    logger.debug(
        f"Fetching slots for {date} (office={office_id}, service={service_id})"
    )
    data = api_client.get("available-appointments-by-office/", params=params)

    if data:
        # Count total appointments across all offices
        total_appointments = sum(
            len(office.get("appointments", [])) for office in data.get("offices", [])
        )
        logger.debug(f"Successfully fetched {total_appointments} slots for {date}")

    return data


def get_available_days(
    start_date, end_date, captcha_token, office_id="10461", service_id="10339028"
):
    """
    Check available days in a date range.
    start_date: e.g. '2025-10-02'
    end_date: e.g. '2026-04-02'
    captcha_token: JWT token from the website
    Returns the available days information.
    """
    api_client = get_api_client()

    params = {
        "startDate": start_date,
        "endDate": end_date,
        "officeId": office_id,
        "serviceId": service_id,
        "serviceCount": "1",
        "captchaToken": captcha_token,
    }

    logger.info(
        f"Checking available days: {start_date} to {end_date} (office={office_id}, service={service_id})"
    )
    data = api_client.get("available-days-by-office/", params=params)

    if data:
        logger.info(f"API response received: {data}")
    else:
        logger.error("Request failed while checking available days")
        print("Request failed")

    return data
