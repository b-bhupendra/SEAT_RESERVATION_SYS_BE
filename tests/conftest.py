"""
Shared test fixtures and configuration for all tests.
Uses an in-memory SQLite database so tests are fully isolated from production data.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Override DATABASE_URL before any app imports ──────────────────────────────
import os
os.environ["DATABASE_URL"] = "sqlite://"  # pure in-memory SQLite

from api.db_core import Base, get_db
from api.index import app

# Shared in-memory engine (same connection for entire test session)
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# SQLite doesn't enforce FK constraints by default – enable them
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the entire test session."""
    # Import all models so SQLAlchemy metadata is populated
    from api.auth_user.model_users import DBUser, DBRole          # noqa: F401
    from api.customers.model_customers import DBCustomer          # noqa: F401
    from api.reservations.model_reservations import DBReservation # noqa: F401
    from api.billing.model_bills import DBBill                    # noqa: F401
    from api.notifications.model_notifications import DBNotification # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provide a clean DB session, auto-rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient with the test DB injected."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def seed_admin(db) -> dict:
    """Insert an admin user and return login credentials."""
    from api.auth_user.model_users import DBUser, DBRole
    from api.auth_user.auth_utils import get_password_hash

    role = DBRole(name="admin", description="Full Access", permissions="all")
    db.add(role)

    user = DBUser(
        email="admin@test.com",
        hashed_password=get_password_hash("secret"),
        role="admin",
        full_name="Test Admin",
    )
    db.add(user)
    db.commit()
    return {"email": "admin@test.com", "password": "secret"}


def get_admin_token(client, db) -> str:
    """Login and return a Bearer token."""
    creds = seed_admin(db)
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
