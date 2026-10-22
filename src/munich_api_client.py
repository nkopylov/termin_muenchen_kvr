"""
Munich API Client - Unified HTTP client for all Munich city API requests.
Centralizes headers, error handling, and request logic.
"""

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Base URL
BASE_API_URL = "https://www48.muenchen.de/buergeransicht/api/citizen"

# Minimal required headers that work for all Munich API endpoints
DEFAULT_HEADERS = {
    "Accept": "application/json",
}


@dataclass(frozen=True)
class ApiResponse:
    """Outcome of a request: JSON data on success, else HTTP status and API error codes"""

    data: dict[str, Any] | None
    status: int | None  # None when no HTTP response arrived
    error_codes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.error_codes


def _error_codes(body: Any) -> tuple[str, ...]:
    """errorCode values of `{"errors": [{"errorCode": ...}]}` or `{"errorCode": ...}`"""
    if not isinstance(body, dict):
        return ()
    codes = [
        e["errorCode"]
        for e in body.get("errors") or []
        if isinstance(e, dict) and e.get("errorCode")
    ]
    if body.get("errorCode"):
        codes.append(body["errorCode"])
    return tuple(codes)


class MunichAPIClient:
    """HTTP client for Munich city appointment API"""

    def __init__(self, timeout: int = 10):
        """
        Initialize API client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.base_url = BASE_API_URL

    def _get_headers(self, content_type: str | None = None) -> dict[str, str]:
        """
        Get headers for request.

        Args:
            content_type: Content-Type header value (for POST requests)

        Returns:
            Headers dictionary
        """
        headers = DEFAULT_HEADERS.copy()
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        Make GET request to Munich API.

        Args:
            endpoint: API endpoint path (e.g., "captcha-challenge/")
            params: Query parameters

        Returns:
            Response JSON data or None on error
        """
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()

        try:
            logger.debug(f"GET {endpoint} with params={params}")
            response = requests.get(
                url, headers=headers, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP {e.response.status_code} error for GET {endpoint}")
            try:
                error_data = e.response.json()
                logger.warning(f"Error details: {error_data}")
            except Exception:
                logger.warning(f"Response text: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for GET {endpoint}: {e}")
            return None

    def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Make POST request to Munich API.

        Args:
            endpoint: API endpoint path (e.g., "captcha-verify/")
            data: JSON data to send

        Returns:
            Response JSON data or None on error
        """
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers(content_type="application/json")

        try:
            logger.debug(f"POST {endpoint}")
            response = requests.post(
                url, headers=headers, json=data, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code} error for POST {endpoint}")
            try:
                error_data = e.response.json()
                logger.error(f"Error details: {error_data}")
            except Exception:
                logger.error(f"Response text: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for POST {endpoint}: {e}")
            return None

    def get_result(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> ApiResponse:
        """GET returning status and API error codes instead of swallowing them"""
        return self._result(
            "GET",
            endpoint,
            lambda url: requests.get(
                url, headers=self._get_headers(), params=params, timeout=self.timeout
            ),
        )

    def post_result(self, endpoint: str, data: dict[str, Any]) -> ApiResponse:
        """POST returning status and API error codes instead of swallowing them"""
        return self._result(
            "POST",
            endpoint,
            lambda url: requests.post(
                url,
                headers=self._get_headers(content_type="application/json"),
                json=data,
                timeout=self.timeout,
            ),
        )

    def _result(self, method: str, endpoint: str, send) -> ApiResponse:
        url = f"{self.base_url}/{endpoint}"
        try:
            response = send(url)
        except Exception as e:
            logger.error(f"Request failed for {method} {endpoint}: {e}")
            return ApiResponse(None, None, ())

        try:
            body = response.json()
        except ValueError:
            body = None

        codes = _error_codes(body)
        if response.ok and not codes:
            return ApiResponse(body, response.status_code, ())
        logger.warning(
            f"HTTP {response.status_code} for {method} {endpoint}, errors={list(codes)}"
        )
        return ApiResponse(None, response.status_code, codes)


# Singleton instance for convenience
_client = None


def get_api_client() -> MunichAPIClient:
    """Get singleton API client instance"""
    global _client
    if _client is None:
        _client = MunichAPIClient()
    return _client
