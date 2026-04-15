"""
Authentication API Tests
Covers: login success, wrong password, missing fields, token structure, RBAC.
"""
import pytest
from tests.conftest import seed_admin, get_admin_token, auth_headers


class TestLogin:

    def test_login_success_returns_token(self, client, db):
        """Valid credentials → 200 with access_token and user info."""
        seed_admin(db)
        resp = client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "secret",
            "role": "admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "admin@test.com"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password_returns_401(self, client, db):
        """Wrong password → 401 Unauthorized."""
        seed_admin(db)
        resp = client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "WRONG",
            "role": "admin",
        })
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self, client, db):
        """Non-existent email → 401 Unauthorized."""
        resp = client.post("/api/auth/login", json={
            "email": "ghost@nowhere.com",
            "password": "secret",
            "role": "admin",
        })
        assert resp.status_code == 401

    def test_login_missing_password_returns_422(self, client, db):
        """Missing required field → 422 Unprocessable Entity."""
        resp = client.post("/api/auth/login", json={"email": "admin@test.com"})
        assert resp.status_code == 422


class TestTokenProtectedRoutes:

    def test_protected_route_without_token_returns_401(self, client, db):
        """Hitting a protected endpoint with no token → 401."""
        resp = client.get("/api/customers")
        assert resp.status_code == 401

    def test_protected_route_with_invalid_token_returns_401(self, client, db):
        """Junk token → 401."""
        resp = client.get("/api/customers", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    def test_protected_route_with_valid_token_succeeds(self, client, db):
        """Valid token → 200."""
        token = get_admin_token(client, db)
        resp = client.get("/api/customers", headers=auth_headers(token))
        assert resp.status_code == 200
