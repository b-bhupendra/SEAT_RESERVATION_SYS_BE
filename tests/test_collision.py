import pytest
from datetime import datetime, timedelta
import uuid
from api.auth_user.model_users import DBUser
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation
from api.billing.model_bills import DBBill
from api.billing.model_plans import DBPlan
from api.notifications.model_notifications import DBNotification
from api.settings.model_settings import DBSetting
from api.reservations.loyalty import calculate_loyalty_and_grace, calculate_fine_and_total
from api.auth_user.auth_utils import get_password_hash

# Helper to generate customer authorization headers
def get_customer_token(client, db, email: str = "customer@test.com", org: str = "Trisha Library", sub_org: str = "Premium Zone") -> str:
    # Check if customer user already exists
    user = db.query(DBUser).filter(DBUser.email == email).first()
    if not user:
        user = DBUser(
            email=email,
            hashed_password=get_password_hash("secret"),
            role="customer",
            full_name="Loyal Customer"
        )
        db.add(user)
        db.commit()

    cust = db.query(DBCustomer).filter(DBCustomer.email == email).first()
    if not cust:
        cust = DBCustomer(
            name="Loyal Customer",
            email=email,
            phone="9999999999",
            status="active",
            organization=org,
            sub_organization=sub_org
        )
        db.add(cust)
        db.commit()

    response = client.post("/api/auth/login", json={"email": email, "password": "secret"})
    assert response.status_code == 200
    return response.json()["access_token"]

def test_loyalty_tier_calculation(db):
    # Setup fresh customer
    cust = DBCustomer(name="John Bronze", email="bronze@test.com", phone="123", status="active", first_contact=datetime.utcnow())
    db.add(cust)
    db.commit()

    # 1. Bronze Tier (0 payments, < 30 days old)
    tier, grace_days = calculate_loyalty_and_grace(db, cust.id)
    assert tier == "Bronze"
    assert grace_days == 2

    # 2. Silver Tier (1 payment and account age >= 30 days)
    cust.first_contact = datetime.utcnow() - timedelta(days=35)
    bill1 = DBBill(customer_id=cust.id, amount=1500, status="paid", due_date=datetime.utcnow(), month_ending=datetime.utcnow())
    db.add(bill1)
    db.commit()
    tier, grace_days = calculate_loyalty_and_grace(db, cust.id)
    assert tier == "Silver"
    assert grace_days == 4

    # 3. Gold Tier (5+ payments)
    for i in range(4):
        b = DBBill(customer_id=cust.id, amount=1500, status="paid", due_date=datetime.utcnow(), month_ending=datetime.utcnow())
        db.add(b)
    db.commit()
    tier, grace_days = calculate_loyalty_and_grace(db, cust.id)
    assert tier == "Gold"
    assert grace_days == 7

def test_late_payment_fine_calculation(db):
    cust = DBCustomer(name="Fine Cust", email="fine@test.com", phone="123", status="active")
    db.add(cust)
    db.commit()

    # Fine disabled
    setting = db.query(DBSetting).filter(DBSetting.key == "enable_late_payment_fine").first()
    if not setting:
        setting = DBSetting(key="enable_late_payment_fine", value="false")
        db.add(setting)
    else:
        setting.value = "false"
    db.commit()

    fine, total = calculate_fine_and_total(db, cust.id, 1500.0, datetime.utcnow() - timedelta(days=1))
    assert fine == 0.0
    assert total == 1500.0

    # Fine enabled
    setting.value = "true"
    db.commit()

    fine, total = calculate_fine_and_total(db, cust.id, 1500.0, datetime.utcnow() - timedelta(days=1))
    assert fine == 250.0
    assert total == 1750.0

def test_prevent_double_booking_and_double_occupying(client, db):
    # Register plans
    p1 = DBPlan(name="Plan Premium", description="Desc", cost=1500)
    db.add(p1)
    db.commit()

    token1 = get_customer_token(client, db, "c1@test.com")
    token2 = get_customer_token(client, db, "c2@test.com")

    # 1. First user occupies a seat
    res = client.post(
        "/api/reservations/occupy",
        json={"seat_number": "TL-PM-001", "organization": "Trisha Library", "sub_organization": "Premium Zone", "plan_cost": 1500.0},
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert res.status_code == 200
    assert "reservation_id" in res.json()

    # 2. Prevent Double Occupying (same user booking another seat)
    res = client.post(
        "/api/reservations/occupy",
        json={"seat_number": "TL-PM-002", "organization": "Trisha Library", "sub_organization": "Premium Zone", "plan_cost": 1500.0},
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert res.status_code == 400
    assert "already have an active or pending reservation" in res.json()["detail"]

    # 3. Prevent Double Booking (another user booking same occupied/held seat)
    res = client.post(
        "/api/reservations/occupy",
        json={"seat_number": "TL-PM-001", "organization": "Trisha Library", "sub_organization": "Premium Zone", "plan_cost": 1500.0},
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert res.status_code == 400
    assert "already occupied or held by another user" in res.json()["detail"]

def test_price_tampering_protection(client, db):
    token = get_customer_token(client, db, "tamper@test.com")
    # Plan is registered with 1500 cost in db. If user passes 10.0, it must be rejected!
    res = client.post(
        "/api/reservations/occupy",
        json={"seat_number": "TL-PM-005", "organization": "Trisha Library", "sub_organization": "Premium Zone", "plan_cost": 10.0},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 400
    assert "Invalid subscription plan cost" in res.json()["detail"]

def test_loyalty_grace_lock_protection(client, db):
    # Seed a plan with cost 1500 to satisfy price validation
    p = DBPlan(name="Plan Premium Grace", description="Desc", cost=1500)
    db.add(p)

    # Old Customer A has paid reservation that expired 1 hour ago
    cust_a = DBCustomer(name="Loyal A", email="cust_a@test.com", phone="1", status="active", first_contact=datetime.utcnow() - timedelta(days=35))
    db.add(cust_a)
    db.flush()
    
    # 1 paid bill -> Silver -> 4 days grace
    b = DBBill(customer_id=cust_a.id, amount=1500, status="paid", due_date=datetime.utcnow() - timedelta(days=32), month_ending=datetime.utcnow() - timedelta(days=2))
    db.add(b)
    
    res_a = DBReservation(
        customer_id=cust_a.id,
        seat_number="TL-PM-010",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow() - timedelta(days=31),
        end_date=datetime.utcnow() - timedelta(hours=1),
        status="paid",
        amount=1500
    )
    db.add(res_a)
    db.commit()

    token_b = get_customer_token(client, db, "cust_b@test.com")

    # Customer B tries to book TL-PM-010 which is under Customer A's active grace period (4 days)
    res = client.post(
        "/api/reservations/occupy",
        json={"seat_number": "TL-PM-010", "organization": "Trisha Library", "sub_organization": "Premium Zone", "plan_cost": 1500.0},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res.status_code == 400
    assert "locked under active late renewal protection" in res.json()["detail"]

def test_collision_resolution_priority_and_refunds(client, db):
    from app.routers.billing import TRANSACTION_USER_MAP

    # 1. Setup Loyal Member A with expired reservation (grace period active)
    cust_a = DBCustomer(name="Loyal Member A", email="member_a@test.com", phone="123", status="active", first_contact=datetime.utcnow() - timedelta(days=35))
    db.add(cust_a)
    db.flush()
    
    # 1 successful payment -> Silver Tier (4 days grace period)
    b_paid = DBBill(customer_id=cust_a.id, amount=1500.0, status="paid", due_date=datetime.utcnow() - timedelta(days=32), month_ending=datetime.utcnow() - timedelta(days=2))
    db.add(b_paid)
    
    res_a = DBReservation(
        customer_id=cust_a.id,
        seat_number="TL-PM-099",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow() - timedelta(days=31),
        end_date=datetime.utcnow() - timedelta(hours=1),
        status="paid",
        amount=1500.0
    )
    db.add(res_a)
    
    # Create renewal pending bill for Member A
    b_pending = DBBill(customer_id=cust_a.id, amount=1500.0, status="pending", due_date=datetime.utcnow(), month_ending=datetime.utcnow() + timedelta(days=30))
    db.add(b_pending)
    db.commit()

    # 2. Setup New Customer B who books and pays for seat TL-PM-099 in the meantime
    cust_b = DBCustomer(name="New User B", email="member_b@test.com", phone="456", status="active", first_contact=datetime.utcnow())
    db.add(cust_b)
    db.flush()
    
    res_b = DBReservation(
        customer_id=cust_b.id,
        seat_number="TL-PM-099",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        status="pending",
        amount=1500.0
    )
    db.add(res_b)
    
    b_b_paid = DBBill(customer_id=cust_b.id, amount=1500.0, status="paid", due_date=datetime.utcnow(), month_ending=datetime.utcnow() + timedelta(days=30))
    db.add(b_b_paid)
    db.commit()

    # 3. Simulate payment check-status success for Loyal Member A
    tx_id = f"tx_{uuid.uuid4().hex}"
    TRANSACTION_USER_MAP[tx_id] = str(cust_a.id)

    # Trigger billing fulfillment simulation
    from app.services.phonepe import PhonePeService
    # Mock PhonePe response to return success
    class MockPhonePe:
        @staticmethod
        async def check_status(transaction_id: str):
            return {"success": True, "status": "PAYMENT_SUCCESS", "transaction_id": transaction_id}
            
    import app.routers.billing as billing_module
    old_service = billing_module.PhonePeService
    billing_module.PhonePeService = MockPhonePe

    try:
        # Fulfill transaction
        res = client.get(f"/api/payment/status/{tx_id}")
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Verify Database States:
        # 1. Member A must be active, reservation renewed
        db.refresh(res_a)
        assert res_a.status == "paid"
        assert res_a.end_date > datetime.utcnow() + timedelta(days=29)

        # Member A bill is now paid
        db.refresh(b_pending)
        assert b_pending.status == "paid"

        # 2. Member B (New guy) reservation must be cancelled
        db.refresh(res_b)
        assert res_b.status == "cancelled"

        # Member B bill must be refunded
        db.refresh(b_b_paid)
        assert b_b_paid.status == "refunded"

        # Refund notification sent to Member B
        notif = db.query(DBNotification).filter(DBNotification.customer_id == cust_b.id).first()
        assert notif is not None
        assert "refunded and cancelled" in notif.message

        # Success notification sent to Member A
        notif_a = db.query(DBNotification).filter(DBNotification.customer_id == cust_a.id).first()
        assert notif_a is not None
        assert "Priority seat protection activated" in notif_a.message

    finally:
        billing_module.PhonePeService = old_service

def test_dynamic_grace_days_settings(db):
    # Setup fresh customer
    cust = DBCustomer(name="Bronze Dynamic", email="bronze_dyn@test.com", phone="123", status="active", first_contact=datetime.utcnow())
    db.add(cust)
    db.flush()
    
    # Assert default bronze grace days is 2
    tier, grace_days = calculate_loyalty_and_grace(db, cust.id)
    assert tier == "Bronze"
    assert grace_days == 2
    
    # Overwrite bronze grace days setting to 5
    setting = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_bronze_days").first()
    if not setting:
        setting = DBSetting(key="loyalty_grace_bronze_days", value="5")
        db.add(setting)
    else:
        setting.value = "5"
    db.commit()
    
    # Assert dynamic grace days reflects new setting value (5)
    tier, grace_days = calculate_loyalty_and_grace(db, cust.id)
    assert tier == "Bronze"
    assert grace_days == 5

def test_collision_resolution_alternative_seat_suggestions(client, db):
    from app.routers.billing import TRANSACTION_USER_MAP
    from api.reservations.model_seats import DBSeat

    # Seed some seats in the same sub_organization
    s1 = DBSeat(seat_number="TL-PM-701", organization="Trisha Library", sub_organization="Premium Zone")
    s2 = DBSeat(seat_number="TL-PM-702", organization="Trisha Library", sub_organization="Premium Zone")
    s3 = DBSeat(seat_number="TL-PM-703", organization="Trisha Library", sub_organization="Premium Zone")
    db.add(s1)
    db.add(s2)
    db.add(s3)
    db.commit()

    cust_a = DBCustomer(name="Loyal Member A", email="member_a_alt@test.com", phone="123", status="active", first_contact=datetime.utcnow() - timedelta(days=35))
    db.add(cust_a)
    db.flush()
    
    # 1 paid bill -> Silver -> 4 days grace
    b_paid = DBBill(customer_id=cust_a.id, amount=1500.0, status="paid", due_date=datetime.utcnow() - timedelta(days=32), month_ending=datetime.utcnow() - timedelta(days=2))
    db.add(b_paid)
    
    res_a = DBReservation(
        customer_id=cust_a.id,
        seat_number="TL-PM-700",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow() - timedelta(days=31),
        end_date=datetime.utcnow() - timedelta(hours=1),
        status="paid",
        amount=1500.0
    )
    db.add(res_a)
    
    b_pending = DBBill(customer_id=cust_a.id, amount=1500.0, status="pending", due_date=datetime.utcnow(), month_ending=datetime.utcnow() + timedelta(days=30))
    db.add(b_pending)
    db.commit()

    cust_b = DBCustomer(name="New User B", email="member_b_alt@test.com", phone="456", status="active", first_contact=datetime.utcnow())
    db.add(cust_b)
    db.flush()
    
    res_b = DBReservation(
        customer_id=cust_b.id,
        seat_number="TL-PM-700",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        status="pending",
        amount=1500.0
    )
    db.add(res_b)
    
    b_b_paid = DBBill(customer_id=cust_b.id, amount=1500.0, status="paid", due_date=datetime.utcnow(), month_ending=datetime.utcnow() + timedelta(days=30))
    db.add(b_b_paid)
    db.commit()

    tx_id = f"tx_alt_{uuid.uuid4().hex}"
    TRANSACTION_USER_MAP[tx_id] = str(cust_a.id)

    from app.services.phonepe import PhonePeService
    class MockPhonePe:
        @staticmethod
        async def check_status(transaction_id: str):
            return {"success": True, "status": "PAYMENT_SUCCESS", "transaction_id": transaction_id}
            
    import app.routers.billing as billing_module
    old_service = billing_module.PhonePeService
    billing_module.PhonePeService = MockPhonePe

    try:
        res = client.get(f"/api/payment/status/{tx_id}")
        assert res.status_code == 200

        # Verify alternative seats were suggested in Member B's notification
        notif = db.query(DBNotification).filter(DBNotification.customer_id == cust_b.id).first()
        assert notif is not None
        assert "available alternative vacant seats" in notif.message
        assert "TL-PM-701" in notif.message
        assert "TL-PM-702" in notif.message
        assert "TL-PM-703" in notif.message

    finally:
        billing_module.PhonePeService = old_service

def test_admin_eviction_dismissal(client, db):
    from tests.conftest import seed_admin, get_admin_token, auth_headers

    # Setup customer with paid seat
    cust = DBCustomer(name="Bad Guy", email="badguy@test.com", phone="111", status="active")
    db.add(cust)
    db.flush()

    res = DBReservation(
        customer_id=cust.id,
        seat_number="TL-PM-800",
        organization="Trisha Library",
        subsection="Premium Zone",
        sub_organization="Premium Zone",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        status="paid",
        amount=1500.0
    )
    db.add(res)
    db.commit()

    # Get admin credentials
    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # Perform eviction call
    evict_res = client.post(
        f"/api/admin/customers/{cust.id}/dismiss",
        json={"reason": "Rules Violation: Making loud noise in study zone"},
        headers=headers
    )
    assert evict_res.status_code == 200
    assert evict_res.json()["status"] == "success"
    assert "badguy@test.com evicted successfully" in evict_res.json()["message"]

    # Verify reservation is now cancelled in DB
    db.refresh(res)
    assert res.status == "cancelled"

    # Verify notification is dispatched
    notif = db.query(DBNotification).filter(DBNotification.customer_id == cust.id).first()
    assert notif is not None
    assert "Administrative Notice: Your seat occupancy has been dismissed/released" in notif.message
    assert "Rules Violation" in notif.message

def test_loyalty_grace_settings_validation_and_lock(client, db):
    from tests.conftest import seed_admin, get_admin_token, auth_headers

    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Assert invalid sequence: Bronze (5) > Silver (3) returns 400 Bad Request
    invalid_res = client.post(
        "/api/settings/loyalty-grace",
        json={"bronze_days": 5, "silver_days": 3, "gold_days": 10},
        headers=headers
    )
    assert invalid_res.status_code == 400
    assert "Invalid grace days sequence" in invalid_res.json()["detail"]

    # 2. Assert valid sequence: Bronze (3) <= Silver (5) <= Gold (10) returns 200 OK
    valid_res = client.post(
        "/api/settings/loyalty-grace",
        json={"bronze_days": 3, "silver_days": 5, "gold_days": 10},
        headers=headers
    )
    assert valid_res.status_code == 200
    assert valid_res.json()["status"] == "success"

    # Verify settings are committed to DB
    bronze_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_bronze_days").first()
    assert bronze_set is not None
    assert bronze_set.value == "3"

    silver_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_silver_days").first()
    assert silver_set.value == "5"

    gold_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_gold_days").first()
    assert gold_set.value == "10"


def test_payment_processing_pause_during_config_update(client, db):
    from tests.conftest import seed_admin, get_admin_token, auth_headers

    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Enable maintenance lock via dedicated /settings/system-lock endpoint
    enable_res = client.post(
        "/api/settings/system-lock",
        json={"value": "true"},
        headers=headers
    )
    assert enable_res.status_code == 200
    assert enable_res.json()["is_updating_config"] == "true"

    # 2. Call status check endpoint during config lock
    tx_id = f"tx_{uuid.uuid4().hex}"
    res = client.get(f"/api/payment/status/{tx_id}")
    
    # Assert it returns 503 Service Unavailable with descriptive suspension message
    assert res.status_code == 503
    assert "temporarily suspended due to administrative configuration updates" in res.json()["detail"]

    # 3. Release config update lock via /settings/system-lock
    release_res = client.post(
        "/api/settings/system-lock",
        json={"value": "false"},
        headers=headers
    )
    assert release_res.status_code == 200

    # Mock payment status response so it doesn't fail on actual check
    from app.services.phonepe import PhonePeService
    class MockPhonePe:
        @staticmethod
        async def check_status(transaction_id: str):
            return {"success": False, "status": "PAYMENT_PENDING", "transaction_id": transaction_id}
            
    import app.routers.billing as billing_module
    old_service = billing_module.PhonePeService
    billing_module.PhonePeService = MockPhonePe

    try:
        res2 = client.get(f"/api/payment/status/{tx_id}")
        # Now it shouldn't raise 503 since lock is released!
        assert res2.status_code == 200
        assert res2.json()["success"] is False
    finally:
        billing_module.PhonePeService = old_service

def test_seat_hold_duration_validation(client, db):
    from tests.conftest import seed_admin, get_admin_token, auth_headers

    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Try to set seat_hold_duration_minutes to an invalid value (0) -> returns 400 Bad Request
    res_zero = client.post(
        "/api/settings/seat_hold_duration_minutes",
        json={"value": "0"},
        headers=headers
    )
    assert res_zero.status_code == 400
    assert "Seat hold duration must be a positive integer" in res_zero.json()["detail"]

    # 2. Try to set seat_hold_duration_minutes to an invalid value (120) -> returns 400 Bad Request
    res_high = client.post(
        "/api/settings/seat_hold_duration_minutes",
        json={"value": "120"},
        headers=headers
    )
    assert res_high.status_code == 400

    # 3. Set seat_hold_duration_minutes to a valid value (20) -> returns 200 OK
    res_valid = client.post(
        "/api/settings/seat_hold_duration_minutes",
        json={"value": "20"},
        headers=headers
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["seat_hold_duration_minutes"] == "20"


def test_role_hierarchical_permissions_expansion(client, db):
    from tests.conftest import seed_admin, get_admin_token, auth_headers
    from api.auth_user.model_users import DBRole

    token = get_admin_token(client, db)
    headers = auth_headers(token)

    # 1. Create a custom role with only "dismiss_customer" permission
    role_res = client.post(
        "/api/roles",
        json={
            "name": "custom_supervisor",
            "description": "Supervisor Role",
            "permissions": "dismiss_customer"
        },
        headers=headers
    )
    assert role_res.status_code == 201
    
    # Assert permissions automatically expanded to include "manage_reservations,view_portal,dismiss_customer"
    created_perms = [p.strip() for p in role_res.json()["permissions"].split(",")]
    assert "dismiss_customer" in created_perms
    assert "manage_reservations" in created_perms
    assert "view_portal" in created_perms

    # 2. Update role using PUT to have only "manage_customers" permission
    update_res = client.put(
        "/api/roles/custom_supervisor",
        json={
            "permissions": "manage_customers",
            "description": "Updated Supervisor Description"
        },
        headers=headers
    )
    assert update_res.status_code == 200
    
    # Assert permissions automatically expanded to include "view_dashboard" and "manage_customers"
    updated_perms = [p.strip() for p in update_res.json()["permissions"].split(",")]
    assert "manage_customers" in updated_perms
    assert "view_dashboard" in updated_perms

def test_payment_polling_idempotency_and_db_persistence(client, db):
    # 1. Setup customer
    cust = DBCustomer(name="Idempotent Member", email="idempotent@test.com", phone="123", status="active", first_contact=datetime.utcnow())
    db.add(cust)
    db.commit()

    # 2. Mock PhonePe check_status success
    from app.services.phonepe import PhonePeService
    class MockPhonePeSuccess:
        @staticmethod
        async def check_status(transaction_id: str):
            return {"success": True, "status": "PAYMENT_SUCCESS", "transaction_id": transaction_id}

    import app.routers.billing as billing_module
    old_service = billing_module.PhonePeService
    billing_module.PhonePeService = MockPhonePeSuccess

    try:
        # Create a DBTransaction manually to simulate a payment that was initiated,
        # and clear TRANSACTION_USER_MAP to simulate a server restart / state loss.
        from app.routers.billing import TRANSACTION_USER_MAP
        tx_id = f"tx_idempotent_{uuid.uuid4().hex}"
        
        # Clear transaction map (simulate restart)
        if tx_id in TRANSACTION_USER_MAP:
            del TRANSACTION_USER_MAP[tx_id]
            
        # Add to DB instead
        from api.billing.model_bills import DBTransaction
        db_txn = DBTransaction(
            transaction_id=tx_id,
            customer_id=cust.id,
            amount=1500.0,
            status="PENDING",
            processed=False
        )
        db.add(db_txn)
        db.commit()

        # Call get_payment_status first time (runs fulfillment)
        res1 = client.get(f"/api/payment/status/{tx_id}")
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # Check that reservation was created/renewed
        res_db1 = db.query(DBReservation).filter(DBReservation.customer_id == cust.id).first()
        assert res_db1 is not None
        assert res_db1.status == "paid"
        end_date_first = res_db1.end_date

        # Call get_payment_status second time (should be idempotent: no-op)
        res2 = client.get(f"/api/payment/status/{tx_id}")
        assert res2.status_code == 200
        assert res2.json()["success"] is True

        # Check that reservation end_date did NOT change!
        db.refresh(res_db1)
        assert res_db1.end_date == end_date_first
        
    finally:
        billing_module.PhonePeService = old_service

