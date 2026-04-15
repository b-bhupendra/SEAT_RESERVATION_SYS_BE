import requests

BASE_URL = "http://localhost:8000/api"

def test_auth():
    # 1. Login
    print("Logging in...")
    login_data = {"email": "admin@lumina.com", "password": "admin123", "role": "admin"}
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code != 200:
        print(f"Login failed: {response.status_code} - {response.text}")
        return

    tokens = response.json()
    token = tokens.get("access_token")
    print(f"Login successful! Token: {token[:20]}...")

    # 2. Access Protected Endpoint
    print("\nAccessing /api/customers...")
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/customers", headers=headers)
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    # 3. Access with Invalid Token
    print("\nAccessing with invalid token...")
    headers = {"Authorization": "Bearer invalid-token"}
    response = requests.get(f"{BASE_URL}/customers", headers=headers)
    print(f"Response Status: {response.status_code}")
    
    # 4. Access with No Token
    print("\nAccessing with no token...")
    response = requests.get(f"{BASE_URL}/customers")
    print(f"Response Status: {response.status_code}")

if __name__ == "__main__":
    test_auth()
