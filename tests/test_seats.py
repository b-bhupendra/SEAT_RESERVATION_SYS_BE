import pytest
from datetime import datetime, timedelta
from api.auth_user.model_users import DBUser, DBRole
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation
from api.reservations.model_seats import DBSeat
from api.settings.model_settings import DBSetting
from tests.conftest import get_admin_token, auth_headers

def test_seat_generation(client, db):
    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Generate seats
    payload = {
        "organization": "Trisha Library",
        "sub_organization": "Premium Zone",
        "prefix": "TL-PM-",
        "count": 5
    }
    resp = client.post("/api/seats/generate", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["count"] == 5

    # 2. Verify seats were created in DB
    seats = db.query(DBSeat).filter(DBSeat.organization == "Trisha Library").all()
    assert len(seats) == 5
    assert seats[0].seat_number == "TL-PM-001"
    assert seats[4].seat_number == "TL-PM-005"

def test_dynamic_seat_statuses(client, db):
    # Setup organization and sub-organization
    org = "Trisha Library"
    sub_org = "Premium Zone"

    # Create 3 seats
    s1 = DBSeat(seat_number="S-001", organization=org, sub_organization=sub_org)
    s2 = DBSeat(seat_number="S-002", organization=org, sub_organization=sub_org)
    s3 = DBSeat(seat_number="S-003", organization=org, sub_organization=sub_org)
    db.add_all([s1, s2, s3])

    # Create customers
    c1 = DBCustomer(name="Cust One", email="cust1@test.com", phone="123", status="active")
    c2 = DBCustomer(name="Cust Two", email="cust2@test.com", phone="456", status="active")
    db.add_all([c1, c2])
    db.commit()

    # Create a paid reservation for seat S-001
    r1 = DBReservation(
        customer_id=c1.id,
        seat_number="S-001",
        subsection=sub_org,
        organization=org,
        sub_organization=sub_org,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        status="paid",
        created_at=datetime.utcnow()
    )

    # Create a pending hold reservation for seat S-002 (active hold)
    r2 = DBReservation(
        customer_id=c2.id,
        seat_number="S-002",
        subsection=sub_org,
        organization=org,
        sub_organization=sub_org,
        start_date=datetime.utcnow(),
        status="pending",
        created_at=datetime.utcnow() # fresh hold
    )

    db.add_all([r1, r2])
    db.commit()

    # 3. Fetch seats list and check status
    resp = client.get(f"/api/seats?organization={org}&sub_organization={sub_org}")
    assert resp.status_code == 200
    seats_list = resp.json()
    assert len(seats_list) == 3

    statuses = {s["seat_number"]: s["status"] for s in seats_list}
    assert statuses["S-001"] == "paid"
    assert statuses["S-002"] == "held"
    assert statuses["S-003"] == "available"

def test_hold_expiration(client, db):
    org = "Trisha Library"
    sub_org = "Premium Zone"

    # Create seat
    s = DBSeat(seat_number="S-010", organization=org, sub_organization=sub_org)
    c = DBCustomer(name="Cust Expire", email="cust_exp@test.com", phone="12345", status="active")
    db.add_all([s, c])
    db.commit()

    # Set hold duration config to 10 minutes
    dur_setting = DBSetting(key="seat_hold_duration_minutes", value="10")
    db.add(dur_setting)
    db.commit()

    # Create a pending hold created 12 minutes ago (expired!)
    r = DBReservation(
        customer_id=c.id,
        seat_number="S-010",
        subsection=sub_org,
        organization=org,
        sub_organization=sub_org,
        start_date=datetime.utcnow() - timedelta(minutes=12),
        status="pending",
        created_at=datetime.utcnow() - timedelta(minutes=12)
    )
    db.add(r)
    db.commit()

    # Query seats list – should trigger cleanup and show seat as available
    resp = client.get(f"/api/seats?organization={org}&sub_organization={sub_org}")
    assert resp.status_code == 200
    seats_list = resp.json()
    
    target_seat = next(x for x in seats_list if x["seat_number"] == "S-010")
    assert target_seat["status"] == "available"

    # Verify reservation status in DB was updated to cancelled
    db.refresh(r)
    assert r.status == "cancelled"

def test_settings_endpoints(client, db):
    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Get settings
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert "seat_hold_duration_minutes" in resp.json()

    # 2. Update setting
    payload = {"value": "20"}
    resp = client.post("/api/settings/seat_hold_duration_minutes", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["seat_hold_duration_minutes"] == "20"

    # Verify DB reflects change
    setting = db.query(DBSetting).filter(DBSetting.key == "seat_hold_duration_minutes").first()
    assert setting.value == "20"

def test_seats_cleanup(client, db):
    org = "Trisha Library"
    sub_org = "Premium Zone"

    # Create seat
    s = DBSeat(seat_number="S-020", organization=org, sub_organization=sub_org)
    c = DBCustomer(name="Cust Expire Cron", email="cust_exp_cron@test.com", phone="123456", status="active")
    db.add_all([s, c])
    db.commit()

    # Set hold duration config to 10 minutes
    dur_setting = DBSetting(key="seat_hold_duration_minutes", value="10")
    db.add(dur_setting)
    db.commit()

    # Create a pending hold created 12 minutes ago (expired!)
    r = DBReservation(
        customer_id=c.id,
        seat_number="S-020",
        subsection=sub_org,
        organization=org,
        sub_organization=sub_org,
        start_date=datetime.utcnow() - timedelta(minutes=12),
        status="pending",
        created_at=datetime.utcnow() - timedelta(minutes=12)
    )
    db.add(r)
    db.commit()

    # Trigger cron cleanup endpoint without token (should succeed unless CRON_SECRET is set)
    resp = client.post("/api/seats/cleanup")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Verify reservation status in DB was updated to cancelled
    db.refresh(r)
    assert r.status == "cancelled"
