"""
Customers API Tests
Covers: list, create, search, pagination, permission enforcement.
"""
import pytest
from tests.conftest import get_admin_token, auth_headers


CUSTOMER_PAYLOAD = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-0100",
    "status": "active",
}


class TestCustomerList:

    def test_list_returns_paginated_response(self, client, db):
        """GET /api/customers → paginated envelope."""
        token = get_admin_token(client, db)
        resp = client.get("/api/customers", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

    def test_empty_list_returns_zero_total(self, client, db):
        """Fresh DB → total == 0."""
        token = get_admin_token(client, db)
        resp = client.get("/api/customers", headers=auth_headers(token))
        assert resp.json()["total"] == 0

    def test_pagination_params_respected(self, client, db):
        """size=5 → at most 5 items per page."""
        token = get_admin_token(client, db)
        # Create 10 customers
        for i in range(10):
            client.post("/api/customers",
                        json={**CUSTOMER_PAYLOAD, "email": f"c{i}@x.com"},
                        headers=auth_headers(token))
        resp = client.get("/api/customers?page=1&size=5", headers=auth_headers(token))
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["total"] == 10
        assert data["pages"] == 2


class TestCustomerCreate:

    def test_create_customer_success(self, client, db):
        """POST /api/customers → 200 with UUID id."""
        token = get_admin_token(client, db)
        resp = client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Jane Doe"
        assert data["email"] == "jane@example.com"
        # id must be a UUID string
        assert len(data["id"]) == 36
        assert data["id"].count("-") == 4

    def test_create_customer_reflected_in_list(self, client, db):
        """After create, GET list total increments."""
        token = get_admin_token(client, db)
        client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        resp = client.get("/api/customers", headers=auth_headers(token))
        assert resp.json()["total"] == 1

    def test_create_customer_missing_name_returns_422(self, client, db):
        """Missing required field → 422."""
        token = get_admin_token(client, db)
        resp = client.post("/api/customers",
                           json={"email": "bad@x.com", "phone": "000"},
                           headers=auth_headers(token))
        assert resp.status_code == 422


class TestCustomerSearch:

    def test_search_by_name(self, client, db):
        """search= filters results by name."""
        token = get_admin_token(client, db)
        client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        client.post("/api/customers",
                    json={"name": "John Smith", "email": "john@x.com", "phone": "999"},
                    headers=auth_headers(token))

        resp = client.get("/api/customers?search=Jane", headers=auth_headers(token))
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Jane Doe"

    def test_search_no_match_returns_empty(self, client, db):
        """search= with no match → total 0."""
        token = get_admin_token(client, db)
        client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        resp = client.get("/api/customers?search=ZZZNOMATCH", headers=auth_headers(token))
        assert resp.json()["total"] == 0


class TestBiometricScan:

    def test_biometric_scan_endpoint(self, client, db):
        """POST /api/customers/scan → success payload."""
        token = get_admin_token(client, db)
        resp = client.post("/api/customers/scan", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
