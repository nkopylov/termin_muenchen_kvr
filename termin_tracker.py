import base64
import hashlib
import json
import logging
import os
import sys
import time

import requests

logger = logging.getLogger(__name__)


def get_captcha_challenge():
    """
    Get a captcha challenge from the server.
    Returns the challenge data dict.
    """
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/captcha-challenge/"

    headers = {
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

    try:
        logger.info("Requesting captcha challenge from server...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        challenge_data = response.json()
        logger.info(f"Captcha challenge received: maxnumber={challenge_data.get('maxnumber', 'unknown')}")
        return challenge_data
    except Exception as e:
        logger.error(f"Failed to get captcha challenge: {e}")
        print(f"Failed to get captcha challenge: {e}")
        return None

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

    logger.info(f"Solving captcha challenge (algorithm={algorithm}, max {maxnumber} iterations)...")
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
                "took": took_ms
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
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/captcha-verify/"

    # Encode solution as base64 JSON payload
    solution_json = json.dumps(solution)
    payload = base64.b64encode(solution_json.encode()).decode()

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

    data = {"payload": payload}

    try:
        logger.info("Verifying captcha solution with server...")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("meta", {}).get("success") and result.get("data", {}).get("valid"):
            token = result.get("token")
            logger.info(f"Captcha token obtained successfully: {token[:50]}...")
            print(f"✓ Got captcha token: {token[:50]}...")
            return token
        else:
            logger.error(f"Captcha verification failed: {result}")
            print(f"Captcha verification failed: {result}")
            return None
    except Exception as e:
        logger.error(f"Captcha verification request failed: {e}")
        print(f"Captcha verification request failed: {e}")
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

def get_available_days(start_date, end_date, captcha_token, office_id="10461", service_id="10339028"):
    """
    Check available days in a date range.
    start_date: e.g. '2025-10-02'
    end_date: e.g. '2026-04-02'
    captcha_token: JWT token from the website
    Returns the available days information.
    """
    url = "https://www48.muenchen.de/buergeransicht/api/citizen/available-days-by-office/"

    params = {
        "startDate": start_date,
        "endDate": end_date,
        "officeId": office_id,
        "serviceId": service_id,
        "serviceCount": "1",
        "captchaToken": captcha_token
    }

    headers = {
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

    try:
        logger.info(f"Checking available days: {start_date} to {end_date} (office={office_id}, service={service_id})")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"API response received: {data}")
        return data
    except Exception as e:
        logger.error(f"Request exception while checking available days: {e}")
        print(f"Request exception: {e}")
        return None

def play_alert():
    """
    Play a simple alert sound (cross-platform)
    """
    if sys.platform == 'darwin':  # macOS
        os.system('afplay /System/Library/Sounds/Glass.aiff')
    elif sys.platform == 'win32':  # Windows
        try:
            import winsound
            winsound.Beep(1000, 500)
        except ImportError:
            print('\a')  # Fallback to terminal bell
    else:  # Linux and others
        print('\a')  # Terminal bell

def check_available_days(start_date, end_date, captcha_token, office_id="10461", service_id="10339028"):
    """
    Checks available days in the date range.
    If any days are available, triggers an alert.
    """
    print(f"Checking available days from {start_date} to {end_date}...")
    data = get_available_days(start_date, end_date, captcha_token, office_id, service_id)

    print("Returned data:", data)

    if isinstance(data, dict):
        if "errorCode" in data:
            print(f"Error code: {data['errorCode']} -- {data.get('errorMessage', '')}")
            return False
        # Check if there are available days in the response
        # The API likely returns a list of available days or similar structure
        if data and len(data) > 0:
            print("Available days detected:", data)
            play_alert()
            return True
    elif isinstance(data, list) and len(data) > 0:
        print("Available days detected:", data)
        play_alert()
        return True

    print("No available days found")
    return False

def main_loop():
    # Configure your search parameters here
    start_date = "2025-10-02"  # Start of date range
    end_date = "2026-04-02"    # End of date range
    office_id = "10461"        # Office ID
    service_id = "10339028"    # Service ID

    # Get a fresh captcha token (solves the proof-of-work automatically)
    print("Getting fresh captcha token...")
    captcha_token = get_fresh_captcha_token()

    if not captcha_token:
        print("Failed to get captcha token. Exiting.")
        return

    # Token is valid for 5 minutes, track when it expires
    token_expires_at = time.time() + 280  # 280 seconds = ~4.5 minutes (buffer before 5min expiry)

    while True:
        # Refresh token if it's about to expire
        if time.time() >= token_expires_at:
            print("\nToken expiring soon, getting a new one...")
            captcha_token = get_fresh_captcha_token()
            if not captcha_token:
                print("Failed to refresh captcha token. Exiting.")
                return
            token_expires_at = time.time() + 280

        if check_available_days(start_date, end_date, captcha_token, office_id, service_id):
            print("Available days found! Stopping monitor.")
            break
        else:
            print("No available days. Checking again in 2 minutes...\n")
        time.sleep(120)

if __name__ == "__main__":
    main_loop()
if __name__ == "__main__":
    main_loop()
if __name__ == "__main__":
    main_loop()
