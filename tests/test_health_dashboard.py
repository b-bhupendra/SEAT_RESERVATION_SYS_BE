"""
Health Check & Dashboard API Tests
Covers: health endpoint, dashboard stats response shape.
"""
import pytest
from tests.conftest import get_admin_token, auth_headers


class TestHealthCheck:

    def test_health_returns_ok(self, client, db):
        """GET /api/health → status ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "db" in data

    def test_health_unauthenticated(self, client, db):
        """Health check is publicly accessible (no auth required)."""
        resp = client.get("/api/health")
        assert resp.status_code == 200


class TestDashboard:

    def test_dashboard_returns_all_stat_keys(self, client, db):
        """GET /api/dashboard → all expected stat keys present."""
        token = get_admin_token(client, db)
        resp = client.get("/api/dashboard", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_customers", "active_reservations", "total_revenue",
                    "usage_rate", "revenue_by_day", "payments_overview"):
            assert key in data, f"Missing key: {key}"

    def test_dashboard_empty_db_zero_stats(self, client, db):
        """With no data, numeric stats should be 0."""
        token = get_admin_token(client, db)
        resp = client.get("/api/dashboard", headers=auth_headers(token))
        data = resp.json()
        assert data["total_customers"] == 0
        assert data["total_revenue"] == 0

    def test_dashboard_revenue_by_day_is_list(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/dashboard", headers=auth_headers(token))
        assert isinstance(resp.json()["revenue_by_day"], list)

    def test_dashboard_payments_overview_is_list(self, client, db):
        token = get_admin_token(client, db)
        resp = client.get("/api/dashboard", headers=auth_headers(token))
        assert isinstance(resp.json()["payments_overview"], list)
