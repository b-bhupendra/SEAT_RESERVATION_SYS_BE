import requests

BASE_URL = "http://localhost:8000/api"

def test_all_domains():
    # 1. Login as Admin
    print("Logging in as Admin...")
    login_data = {"email": "admin@lumina.com", "password": "admin123", "role": "admin"}
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    token = response.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Login successful!")

    # 2. Test Customer Domain
    print("\nTesting Customers API...")
    response = requests.get(f"{BASE_URL}/customers", headers=headers)
    print(f"GET /customers Status: {response.status_code}")

    # 3. Test Billing Domain
    print("\nTesting Billing API...")
    response = requests.get(f"{BASE_URL}/bills", headers=headers)
    print(f"GET /bills Status: {response.status_code}")

    # 4. Test Reservations Domain
    print("\nTesting Reservations API...")
    response = requests.get(f"{BASE_URL}/reservations", headers=headers)
    print(f"GET /reservations Status: {response.status_code}")

    # 5. Test Notifications Domain
    print("\nTesting Notifications API...")
    response = requests.get(f"{BASE_URL}/notifications", headers=headers)
    print(f"GET /notifications Status: {response.status_code}")

    # 6. Test RBAC (Staff access to bills - allowed for staff?)
    # Based on route_reservations.py: ALL_ROLES = ["admin", "manager", "staff"]
    # So staff should be able to GET all.
    print("\nLogging in as Staff...")
    login_data_staff = {"email": "staff@lumina.com", "password": "staff123", "role": "staff"}
    response_staff = requests.post(f"{BASE_URL}/auth/login", json=login_data_staff)
    token_staff = response_staff.json().get("access_token")
    headers_staff = {"Authorization": f"Bearer {token_staff}"}
    
    print("Staff accessing /bills (should be allowed)...")
    response = requests.get(f"{BASE_URL}/bills", headers=headers_staff)
    print(f"GET /bills Status: {response.status_code}")

if __name__ == "__main__":
    try:
        test_all_domains()
    except Exception as e:
        print(f"Error during testing: {e}")
