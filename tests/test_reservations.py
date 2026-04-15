"""
Reservations API Tests
Covers: list, create, status update with UUID path params, pagination.
"""
import pytest
from datetime import datetime, timedelta
from tests.conftest import get_admin_token, auth_headers


def create_customer(client, token):
    """Helper: create and return a customer dict."""
    resp = client.post("/api/customers", json={
        "name": "Test Customer",
        "email": "tc@example.com",
        "phone": "555-9999",
        "status": "active",
    }, headers=auth_headers(token))
    assert resp.status_code == 200
    return resp.json()


def reservation_payload(customer_id: str) -> dict:
    now = datetime.utcnow()
    return {
        "customer_id": customer_id,
        "subsection": "A",
        "seat_number": "A1",
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(days=30)).isoformat(),
        "duration_months": 1,
        "amount": 150.00,
        "pay_via": "Cash",
        "status": "paid",
    }


class TestReservationList:

    def test_list_returns_paginated_envelope(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/reservations", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        for key in ("items", "total", "page", "pages"):
            assert key in data

    def test_empty_db_returns_zero_total(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/reservations", headers=auth_headers(token))
        assert resp.json()["total"] == 0


class TestReservationCreate:

    def test_create_reservation_returns_uuid_id(self, client, db):
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        payload = reservation_payload(customer["id"])
        resp = client.post("/api/reservations", json=payload, headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["id"]) == 36
        assert data["customer_id"] == customer["id"]
        assert data["seat_number"] == "A1"

    def test_create_reservation_increments_list(self, client, db):
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        client.post("/api/reservations",
                    json=reservation_payload(customer["id"]),
                    headers=auth_headers(token))
        resp = client.get("/api/reservations", headers=auth_headers(token))
        assert resp.json()["total"] == 1

    def test_create_reservation_missing_field_returns_422(self, client, db):
        token = get_admin_token(client, db)
        resp = client.post("/api/reservations",
                           json={"seat_number": "B2"},  # missing required fields
                           headers=auth_headers(token))
        assert resp.status_code == 422

    def test_reservation_id_is_valid_uuid(self, client, db):
        """UUID format check: 8-4-4-4-12 character groups."""
        import re
        UUID_REGEX = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        )
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        resp = client.post("/api/reservations",
                           json=reservation_payload(customer["id"]),
                           headers=auth_headers(token))
        assert UUID_REGEX.match(resp.json()["id"])


class TestReservationStatusUpdate:

    def test_patch_status_with_uuid_succeeds(self, client, db):
        """PATCH /api/reservations/{uuid}/status → 200."""
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        create_resp = client.post("/api/reservations",
                                  json=reservation_payload(customer["id"]),
                                  headers=auth_headers(token))
        res_id = create_resp.json()["id"]

        patch_resp = client.patch(
            f"/api/reservations/{res_id}/status",
            json={"status": "cancelled"},
            headers=auth_headers(token),
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "updated"

    def test_patch_non_existent_reservation_returns_404(self, client, db):
        """Patching a fake UUID → 404."""
        import uuid
        token = get_admin_token(client, db)
        fake_id = str(uuid.uuid4())
        resp = client.patch(
            f"/api/reservations/{fake_id}/status",
            json={"status": "cancelled"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 404

    def test_patch_with_integer_id_returns_422(self, client, db):
        """Passing an integer instead of UUID → 422 Unprocessable Entity."""
        token = get_admin_token(client, db)
        resp = client.patch(
            "/api/reservations/999/status",
            json={"status": "cancelled"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 422
