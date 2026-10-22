# ABOUTME: Tests for the Munich citizen API integration: ALTCHA captcha and availability calendar.
# ABOUTME: Solver tests use a server-verified challenge; the rest call the live API.
"""
Tests for termin_tracker.py
"""

import base64
import json
from datetime import date, timedelta

import pytest

from src.services_manager import get_full_payload
from src.termin_tracker import (
    build_captcha_payload,
    get_available_days,
    get_available_slots,
    get_fresh_captcha_token,
    solve_captcha_challenge,
)

# Challenge issued by /captcha-challenge/ whose solution /captcha-verify/ accepted as valid
VERIFIED_CHALLENGE = {
    "parameters": {
        "algorithm": "SHA-256",
        "nonce": "1223b58fc6de7ae093f0b321929e22b2",
        "salt": "59f1a11ddb971e2ba4146ab5bfd18f19",
        "cost": 1000,
        "keyLength": 32,
        "keyPrefix": "00",
        "keySignature": None,
        "memoryCost": None,
        "parallelism": None,
        "expiresAt": 1792657321,
        "data": None,
    },
    "signature": "05e66aaeb5c703721c3f651f4f68e2b352c9bb1c2233786403178fb951c863a6",
}
VERIFIED_COUNTER = 445
VERIFIED_DERIVED_KEY = (
    "0092ff25683c8ca1dae2bbb79a28f827b8d86ff8ac87d8dcdef0e71b4b914083"
)


class TestCaptchaSolver:
    def test_solves_server_verified_challenge(self):
        solution = solve_captcha_challenge(VERIFIED_CHALLENGE)

        assert solution["counter"] == VERIFIED_COUNTER
        assert solution["derivedKey"] == VERIFIED_DERIVED_KEY
        assert isinstance(solution["time"], float)

    def test_rejects_unsupported_algorithm(self, caplog):
        challenge = {
            "parameters": {
                **VERIFIED_CHALLENGE["parameters"],
                "algorithm": "ARGON2ID",
            },
            "signature": VERIFIED_CHALLENGE["signature"],
        }

        assert solve_captcha_challenge(challenge) is None
        assert "Unsupported captcha algorithm: ARGON2ID" in caplog.text

    def test_payload_contains_challenge_and_solution(self):
        solution = {
            "counter": VERIFIED_COUNTER,
            "derivedKey": VERIFIED_DERIVED_KEY,
            "time": 12.5,
        }

        payload = build_captcha_payload(VERIFIED_CHALLENGE, solution)

        assert json.loads(base64.b64decode(payload)) == {
            "challenge": VERIFIED_CHALLENGE,
            "solution": solution,
        }


@pytest.mark.asyncio
async def test_fresh_captcha_token_is_jwt():
    token = await get_fresh_captcha_token()

    assert token is not None
    assert token.count(".") == 2


@pytest.fixture(scope="module")
def bookable_service():
    """Find a live service/office with bookable days: (service_id, office_id, days)."""
    import asyncio

    token = asyncio.run(get_fresh_captcha_token())
    payload = get_full_payload()
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=90)).isoformat()
    candidates = [
        s
        for s in payload["services"]
        if any(word in s["name"] for word in ("Fahrzeug", "Personalausweis"))
    ]
    for service in candidates[:10]:
        office_ids = [
            r["officeId"]
            for r in payload["relations"]
            if r["serviceId"] == service["id"] and r.get("public", True)
        ]
        for office_id in office_ids[:3]:
            data = get_available_days(
                start, end, token, str(office_id), str(service["id"])
            )
            if data and data["availableDays"]:
                return token, service["id"], office_id, data["availableDays"]
    pytest.skip("No bookable appointments found in the live system")


class TestAvailability:
    def test_available_days_lists_dates(self, bookable_service):
        _, _, _, days = bookable_service

        for day in days:
            date.fromisoformat(day["date"])

    def test_available_slots_for_last_bookable_day(self, bookable_service):
        token, service_id, office_id, days = bookable_service
        last_day = days[-1]["date"]

        slots = get_available_slots(last_day, str(office_id), str(service_id), token)

        appointments = [
            ts for office in slots["offices"] for ts in office["appointments"]
        ]
        assert appointments
        assert all(isinstance(ts, int) for ts in appointments)

    def test_auslaenderbehoerde_requires_captcha_token(self, caplog):
        start = date.today().isoformat()
        end = (date.today() + timedelta(days=30)).isoformat()

        assert get_available_days(start, end, "", "10461", "10339028") is None
        assert "captchaMissing" in caplog.text
