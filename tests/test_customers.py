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


def seed_staff(db) -> dict:
    from api.auth_user.model_users import DBUser, DBRole
    from api.auth_user.auth_utils import get_password_hash

    role = db.query(DBRole).filter(DBRole.name == "staff").first()
    if not role:
        role = DBRole(name="staff", description="Staff User", permissions="view_portal,view_notifications,manage_customers")
        db.add(role)

    user = DBUser(
        email="staff@test.com",
        hashed_password=get_password_hash("secret"),
        role="staff",
        full_name="Test Staff",
    )
    db.add(user)
    db.commit()
    return {"email": "staff@test.com", "password": "secret"}


def get_staff_token(client, db) -> str:
    creds = seed_staff(db)
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200
    return response.json()["access_token"]


class TestCustomerEditAndDelete:

    def test_update_customer_success(self, client, db):
        """PUT /api/customers/{id} successfully updates details and user syncs."""
        token = get_admin_token(client, db)
        
        # Create customer
        create_resp = client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]

        # Update details
        update_payload = {
            "name": "Jane Updated",
            "email": "jane_updated@example.com",
            "phone": "555-9999",
            "status": "active",
            "organization": "G2 Library",
            "sub_organization": "Reading Room"
        }
        update_resp = client.put(f"/api/customers/{customer_id}", json=update_payload, headers=auth_headers(token))
        assert update_resp.status_code == 200
        updated_data = update_resp.json()
        assert updated_data["name"] == "Jane Updated"
        assert updated_data["email"] == "jane_updated@example.com"
        assert updated_data["phone"] == "555-9999"
        assert updated_data["organization"] == "G2 Library"
        assert updated_data["sub_organization"] == "Reading Room"

    def test_delete_customer_success_by_admin(self, client, db):
        """DELETE /api/customers/{id} successfully deletes customer and all records as admin."""
        token = get_admin_token(client, db)

        # Create customer
        create_resp = client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(token))
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]

        # Delete customer
        delete_resp = client.delete(f"/api/customers/{customer_id}", headers=auth_headers(token))
        assert delete_resp.status_code == 200
        assert delete_resp.json()["msg"] == "Customer and associated user account successfully deleted."

        # Fetch list to verify deletion
        list_resp = client.get("/api/customers", headers=auth_headers(token))
        assert list_resp.json()["total"] == 0

    def test_delete_customer_forbidden_for_staff(self, client, db):
        """DELETE /api/customers/{id} returns 403 Forbidden for staff lacking dismiss_customer."""
        admin_token = get_admin_token(client, db)
        staff_token = get_staff_token(client, db)

        # Create customer
        create_resp = client.post("/api/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers(admin_token))
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]

        # Attempt delete as staff
        delete_resp = client.delete(f"/api/customers/{customer_id}", headers=auth_headers(staff_token))
        assert delete_resp.status_code == 403

