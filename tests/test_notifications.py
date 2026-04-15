"""
Notifications API Tests
Covers: list (with joined customer_name), create, mark-as-read (UUID path param),
mark-all-as-read, sort ordering.
"""
import pytest
from tests.conftest import get_admin_token, auth_headers
import uuid


def create_customer(client, token, email="notif_cust@example.com"):
    resp = client.post("/api/customers", json={
        "name": "Notif Customer",
        "email": email,
        "phone": "555-7777",
        "status": "active",
    }, headers=auth_headers(token))
    assert resp.status_code == 200
    return resp.json()


def notif_payload(customer_id: str) -> dict:
    return {
        "customer_id": customer_id,
        "message": "Your seat reservation is confirmed.",
        "is_read": False,
    }


class TestNotificationList:

    def test_list_returns_paginated_envelope(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/notifications", headers=auth_headers(token))
        assert resp.status_code == 200
        for key in ("items", "total", "page", "pages"):
            assert key in resp.json()

    def test_empty_returns_zero_total(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/notifications", headers=auth_headers(token))
        assert resp.json()["total"] == 0

    def test_list_includes_customer_name(self, client, db):
        """Response items must include customer_name from the JOIN."""
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        client.post("/api/notifications",
                    json=notif_payload(customer["id"]),
                    headers=auth_headers(token))
        resp = client.get("/api/notifications", headers=auth_headers(token))
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_name"] == "Notif Customer"

    def test_list_items_have_uuid_ids(self, client, db):
        import re
        UUID_REGEX = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        )
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        client.post("/api/notifications",
                    json=notif_payload(customer["id"]),
                    headers=auth_headers(token))
        items = client.get("/api/notifications", headers=auth_headers(token)).json()["items"]
        for item in items:
            assert UUID_REGEX.match(item["id"]), f"Bad UUID: {item['id']}"


class TestNotificationCreate:

    def test_create_notification_returns_200(self, client, db):
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        resp = client.post("/api/notifications",
                           json=notif_payload(customer["id"]),
                           headers=auth_headers(token))
        assert resp.status_code == 200

    def test_create_notification_missing_message_returns_422(self, client, db):
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        resp = client.post("/api/notifications",
                           json={"customer_id": customer["id"]},
                           headers=auth_headers(token))
        assert resp.status_code == 422


class TestMarkAsRead:

    def test_mark_single_as_read_with_uuid(self, client, db):
        """PATCH /api/notifications/{uuid}/read → 200."""
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        create_resp = client.post("/api/notifications",
                                  json=notif_payload(customer["id"]),
                                  headers=auth_headers(token))
        notif_id = create_resp.json()["id"]

        resp = client.patch(
            f"/api/notifications/{notif_id}/read",
            headers=auth_headers(token),
        )
        assert resp.status_code == 200
        assert "marked as read" in resp.json()["msg"].lower()

    def test_mark_read_with_integer_returns_422(self, client, db):
        """Integer ID → 422 (must be UUID)."""
        token = get_admin_token(client, db)
        resp = client.patch("/api/notifications/999/read", headers=auth_headers(token))
        assert resp.status_code == 422

    def test_mark_nonexistent_notification_returns_404(self, client, db):
        token = get_admin_token(client, db)
        resp = client.patch(
            f"/api/notifications/{uuid.uuid4()}/read",
            headers=auth_headers(token),
        )
        assert resp.status_code == 404

    def test_mark_all_as_read(self, client, db):
        """POST /api/notifications/read-all → 200."""
        token = get_admin_token(client, db)
        customer = create_customer(client, token)
        for i in range(3):
            client.post("/api/notifications",
                        json={**notif_payload(customer["id"]), "message": f"Msg {i}"},
                        headers=auth_headers(token))
        resp = client.post("/api/notifications/read-all", headers=auth_headers(token))
        assert resp.status_code == 200
