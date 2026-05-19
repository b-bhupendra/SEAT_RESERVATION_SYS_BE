import pytest
from datetime import datetime, timedelta
from tests.conftest import auth_headers
from api.auth_user.model_users import DBUser, DBRole
from api.customers.model_customers import DBCustomer
from api.billing.model_bills import DBBill
from api.auth_user.auth_utils import get_password_hash

def seed_test_roles_and_users(db):
    # Ensure role is created if not exists
    cust_role = db.query(DBRole).filter(DBRole.name == "customer").first()
    if not cust_role:
        cust_role = DBRole(name="customer", description="Customer Role", permissions="view_portal,view_notifications")
        db.add(cust_role)
    
    admin_role = db.query(DBRole).filter(DBRole.name == "admin").first()
    if not admin_role:
        admin_role = DBRole(name="admin", description="Admin Role", permissions="all")
        db.add(admin_role)

    staff_role = db.query(DBRole).filter(DBRole.name == "staff").first()
    if not staff_role:
        staff_role = DBRole(name="staff", description="Staff Role", permissions="manage_reservations")
        db.add(staff_role)

    db.commit()

def create_customer_with_user(db, name, email, password, role="customer"):
    user = DBUser(
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        full_name=name
    )
    db.add(user)
    db.flush()

    customer = DBCustomer(
        name=name,
        email=email,
        phone="111-222-333",
        status="active",
        user_id=user.id,
        first_contact=datetime.utcnow()
    )
    db.add(customer)
    db.commit()
    return customer, user

def login_user(client, email, password):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]

def test_customer_retrieves_only_own_bills(client, db):
    seed_test_roles_and_users(db)
    
    # 1. Create two customers with users
    cust_a, user_a = create_customer_with_user(db, "Customer A", "cust_a@test.com", "pass123")
    cust_b, user_b = create_customer_with_user(db, "Customer B", "cust_b@test.com", "pass123")
    
    # 2. Add bills for both customers
    now = datetime.utcnow()
    bill_a = DBBill(
        customer_id=cust_a.id,
        amount=1500.0,
        month_ending=now,
        due_date=now + timedelta(days=5),
        status="pending",
        pay_via="UPI"
    )
    bill_b = DBBill(
        customer_id=cust_b.id,
        amount=2500.0,
        month_ending=now,
        due_date=now + timedelta(days=5),
        status="paid",
        pay_via="Cash"
    )
    db.add(bill_a)
    db.add(bill_b)
    db.commit()

    # 3. Login as Customer A and fetch /api/me/bills
    token_a = login_user(client, "cust_a@test.com", "pass123")
    res_a = client.get("/api/me/bills", headers=auth_headers(token_a))
    assert res_a.status_code == 200
    bills_a = res_a.json()
    assert len(bills_a) == 1
    assert bills_a[0]["amount"] == 1500.0
    assert bills_a[0]["customer_name"] == "Customer A"
    assert bills_a[0]["status"] == "pending"

    # 4. Login as Customer B and fetch /api/me/bills
    token_b = login_user(client, "cust_b@test.com", "pass123")
    res_b = client.get("/api/me/bills", headers=auth_headers(token_b))
    assert res_b.status_code == 200
    bills_b = res_b.json()
    assert len(bills_b) == 1
    assert bills_b[0]["amount"] == 2500.0
    assert bills_b[0]["customer_name"] == "Customer B"
    assert bills_b[0]["status"] == "paid"

def test_get_my_bills_requires_view_portal_ability(client, db):
    seed_test_roles_and_users(db)
    
    # Create a staff user (whose role has "manage_reservations" but NOT "view_portal" permission/ability)
    staff_user = DBUser(
        email="staff_no_portal@test.com",
        hashed_password=get_password_hash("pass123"),
        role="staff",
        full_name="Staff No Portal"
    )
    db.add(staff_user)
    db.commit()

    token = login_user(client, "staff_no_portal@test.com", "pass123")
    res = client.get("/api/me/bills", headers=auth_headers(token))
    
    # Check that it returns 403 Forbidden because staff role doesn't have "view_portal" ability
    assert res.status_code == 403
    assert "view_portal" in res.json()["detail"]

def test_get_my_bills_unauthorized_for_anonymous_user(client, db):
    res = client.get("/api/me/bills")
    assert res.status_code == 401
