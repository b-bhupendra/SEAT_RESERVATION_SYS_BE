"""
Integration Tests - End-to-End Flows
Covers complete user journeys across multiple modules.
"""
import pytest
from datetime import datetime, timedelta
from tests.conftest import get_admin_token, auth_headers


class TestFullReservationFlow:
    """
    Create customer → create reservation → update status → verify in list.
    This is the core business flow of the seat reservation system.
    """

    def test_full_reservation_lifecycle(self, client, db):
        token = get_admin_token(client, db)
        headers = auth_headers(token)

        # 1. Create a customer
        customer = client.post("/api/customers", json={
            "name": "Alice Flow",
            "email": "alice@flow.com",
            "phone": "555-2222",
            "status": "active",
        }, headers=headers).json()
        assert customer["id"]

        # 2. Create a reservation for that customer
        now = datetime.utcnow()
        res = client.post("/api/reservations", json={
            "customer_id": customer["id"],
            "subsection": "B",
            "seat_number": "B12",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=30)).isoformat(),
            "duration_months": 1,
            "amount": 200.00,
            "pay_via": "GCash",
            "status": "paid",
        }, headers=headers).json()
        assert res["seat_number"] == "B12"
        res_id = res["id"]

        # 3. Verify it appears in the list
        list_resp = client.get("/api/reservations", headers=headers)
        ids_in_list = [r["id"] for r in list_resp.json()["items"]]
        assert res_id in ids_in_list

        # 4. Update status to cancelled
        patch = client.patch(f"/api/reservations/{res_id}/status",
                             json={"status": "cancelled"},
                             headers=headers)
        assert patch.status_code == 200

    def test_full_billing_lifecycle(self, client, db):
        """Create customer → create bill → verify in list → mark paid."""
        token = get_admin_token(client, db)
        headers = auth_headers(token)

        customer = client.post("/api/customers", json={
            "name": "Bob Billing",
            "email": "bob@billing.com",
            "phone": "555-3333",
            "status": "active",
        }, headers=headers).json()

        now = datetime.utcnow()
        bill = client.post("/api/bills", json={
            "customer_id": customer["id"],
            "amount": 500.00,
            "month_ending": now.isoformat(),
            "due_date": (now + timedelta(days=15)).isoformat(),
            "pay_via": "Bank Transfer",
        }, headers=headers).json()

        assert bill["status"] == "pending"
        assert bill["customer_name"] == "Bob Billing"

        # Verify in list
        bills = client.get("/api/bills", headers=headers).json()
        assert bills["total"] == 1

        # Mark as paid
        resp = client.patch(f"/api/bills/{bill['id']}/status",
                            json={"status": "paid"}, headers=headers)
        assert resp.status_code == 200

    def test_full_notification_flow(self, client, db):
        """Create customer → send notification → notifications appear in list → mark as read."""
        token = get_admin_token(client, db)
        headers = auth_headers(token)

        customer = client.post("/api/customers", json={
            "name": "Carol Notif",
            "email": "carol@notif.com",
            "phone": "555-4444",
            "status": "active",
        }, headers=headers).json()

        # Send notification
        notif_resp = client.post("/api/notifications", json={
            "customer_id": customer["id"],
            "message": "Welcome to Lumina Pro!",
            "is_read": False,
        }, headers=headers)
        assert notif_resp.status_code == 200
        notif_id = notif_resp.json()["id"]

        # Verify in list with customer name
        list_resp = client.get("/api/notifications", headers=headers)
        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_name"] == "Carol Notif"
        assert items[0]["is_read"] is False

        # Mark as read
        read_resp = client.patch(f"/api/notifications/{notif_id}/read", headers=headers)
        assert read_resp.status_code == 200


class TestRBACEnforcement:
    """Role-Based Access Control must block insufficient privileges."""

    def _get_staff_token(self, client, db):
        from api.auth_user.model_users import DBUser, DBRole
        from api.auth_user.auth_utils import get_password_hash

        role = DBRole(name="staff", description="Staff", permissions="read")
        db.add(role)
        user = DBUser(
            email="staff@test.com",
            hashed_password=get_password_hash("staffpass"),
            role="staff",
            full_name="Staff User",
        )
        db.add(user)
        db.commit()
        resp = client.post("/api/auth/login", json={
            "email": "staff@test.com",
            "password": "staffpass",
            "role": "staff",
        })
        return resp.json()["access_token"]

    def test_staff_cannot_create_customer(self, client, db):
        """Staff role → 403 on create customer."""
        token = self._get_staff_token(client, db)
        resp = client.post("/api/customers", json={
            "name": "Blocked",
            "email": "blocked@x.com",
            "phone": "000",
            "status": "active",
        }, headers=auth_headers(token))
        assert resp.status_code == 403

    def test_staff_can_read_customers(self, client, db):
        """Staff role can still LIST customers."""
        token = self._get_staff_token(client, db)
        resp = client.get("/api/customers", headers=auth_headers(token))
        assert resp.status_code == 200
