# ABOUTME: Tests for the service catalog manager (categories, service lookup).
# ABOUTME: These read the live city catalog.

import pytest

from src import services_manager
from src.services_manager import categorize_services, get_service_info


class TestServicesManager:
    """Tests for services_manager.py business logic"""

    def test_categorize_services_returns_dict(self):
        """Test categorize_services returns a dictionary"""
        categories = categorize_services()
        assert isinstance(categories, dict)

    def test_categorize_services_has_categories(self):
        """Test categorize_services returns non-empty categories"""
        categories = categorize_services()
        assert len(categories) > 0

    def test_categorize_services_structure(self):
        """Test each category contains a list of services"""
        categories = categorize_services()
        for category_name, services in categories.items():
            assert isinstance(category_name, str)
            assert isinstance(services, list)
            assert len(services) > 0

    def test_categorize_services_service_structure(self):
        """Test each service has required fields"""
        categories = categorize_services()
        for services in categories.values():
            for service in services:
                assert "id" in service
                assert "name" in service
                assert isinstance(service["id"], int)
                assert isinstance(service["name"], str)

    def test_get_service_info_valid_id(self):
        """Test get_service_info returns correct service"""
        # First get all services to find a valid ID
        categories = categorize_services()
        first_service = None
        for services in categories.values():
            if services:
                first_service = services[0]
                break

        assert first_service is not None

        # Get info for that service
        service_info = get_service_info(first_service["id"])
        assert service_info is not None
        assert service_info["id"] == first_service["id"]
        assert service_info["name"] == first_service["name"]

    def test_get_service_info_invalid_id(self):
        """Test get_service_info returns None for invalid ID"""
        service_info = get_service_info(999999)
        assert service_info is None

    def test_get_service_info_returns_complete_data(self):
        """Test get_service_info returns all expected fields"""
        categories = categorize_services()
        first_service = None
        for services in categories.values():
            if services:
                first_service = services[0]
                break

        service_info = get_service_info(first_service["id"])
        assert "id" in service_info
        assert "name" in service_info
        # Note: get_service_info returns raw service dict, not with category field
        # Category is retrieved separately via get_category_for_service


PAYLOAD = {
    "services": [{"id": 1, "name": "Alt"}],
    "offices": [{"id": 10, "name": "Bürgerbüro Pasing"}],
    "relations": [{"serviceId": 1, "officeId": 10, "public": True}],
}


@pytest.fixture
def cached_catalog(monkeypatch):
    monkeypatch.setattr(services_manager, "_services_cache", PAYLOAD["services"])
    monkeypatch.setattr(services_manager, "_full_payload_cache", PAYLOAD)


class TestRefreshCatalog:
    def test_success_replaces_caches(self, cached_catalog, monkeypatch):
        fresh = {
            "services": [{"id": 2, "name": "Neu"}],
            "offices": [],
            "relations": [],
        }
        monkeypatch.setattr(services_manager, "fetch_full_payload", lambda: fresh)

        assert services_manager.refresh_catalog() is True
        assert services_manager.get_full_payload() == fresh
        assert services_manager.get_services() == [{"id": 2, "name": "Neu"}]

    @pytest.mark.parametrize("failed", [None, {}, {"services": []}])
    def test_failure_keeps_caches(self, cached_catalog, monkeypatch, failed):
        monkeypatch.setattr(services_manager, "fetch_full_payload", lambda: failed)

        assert services_manager.refresh_catalog() is False
        assert services_manager.get_full_payload() == PAYLOAD
        assert services_manager.get_services() == PAYLOAD["services"]


class TestOfficeFallback:
    @pytest.mark.parametrize(
        ("lang", "expected"),
        [(None, "Office 99"), ("en", "Office 99"), ("ru", "Отделение 99")],
    )
    def test_unknown_office(self, cached_catalog, lang, expected):
        assert services_manager.get_office_name(99, lang) == expected

    def test_known_office(self, cached_catalog):
        assert services_manager.get_office_name(10, "ru") == "Bürgerbüro Pasing"
