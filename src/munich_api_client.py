"""
Munich API Client - Unified HTTP client for all Munich city API requests.
Centralizes headers, error handling, and request logic.
"""

import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Base URLs
BASE_API_URL = "https://www48.muenchen.de/buergeransicht/api/citizen"
BASE_REFERRER = "https://stadt.muenchen.de/"

# Minimal required headers that work for all Munich API endpoints
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://stadt.muenchen.de",
    "Referer": "https://stadt.muenchen.de/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
}


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

    def _get_headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
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
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
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

    def post(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    def get_full_url(self, path: str) -> str:
        """
        Get full URL for an API endpoint.

        Args:
            path: Endpoint path

        Returns:
            Full URL
        """
        return f"{self.base_url}/{path}"


# Singleton instance for convenience
_client = None


def get_api_client() -> MunichAPIClient:
    """Get singleton API client instance"""
    global _client
    if _client is None:
        _client = MunichAPIClient()
    return _client
