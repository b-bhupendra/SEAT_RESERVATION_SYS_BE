import os
import hashlib
import base64
import json
import httpx
import uuid
from typing import Dict, Any

from dotenv import load_dotenv

load_dotenv()

# Configuration
ENV = os.getenv("ENV", "development")
PHONEPE_SIMULATION = os.getenv("PHONEPE_SIMULATION", "false").lower() == "true"

MERCHANT_ID = os.getenv("MERCHANT_ID", "MOCK_MERCHANT")
SALT_KEY = os.getenv("SALT_KEY", "mock-salt-key")
SALT_INDEX = os.getenv("SALT_INDEX", "1")

if ENV == "production":
    BASE_URL = "https://api.phonepe.com/apis/hermes"
else:
    BASE_URL = "https://api-preprod.phonepe.com/apis/pg-sandbox"


class PhonePeService:
    @staticmethod
    def generate_checksum(payload_base64: str, endpoint: str) -> str:
        """
        Implements the PhonePe checksum formula:
        SHA256(Base64_Payload + Endpoint + Salt_Key) + "###" + Salt_Index
        """
        string_to_hash = payload_base64 + endpoint + SALT_KEY
        hashed_string = hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()
        return f"{hashed_string}###{SALT_INDEX}"

    @staticmethod
    async def initiate_payment(data: dict) -> Dict[str, Any]:
        """
        Initiates a payment request via PhonePe Gateway.
        Includes a Simulation Mode to bypass real network calls during local development.
        """
        transaction_id = f"TXN_{uuid.uuid4().hex[:16]}"
        amount_paise = int(data.get("amount", 0) * 100) # PhonePe expects amount in paise
        
        # In simulation mode, return a mock redirect URL immediately
        if ENV == "development" and PHONEPE_SIMULATION:
            return {
                "success": True,
                "redirect_url": f"http://localhost:5173/app/billing?sim_success=true&txn={transaction_id}",
                "transaction_id": transaction_id,
                "message": "[SIMULATION] Payment initiated successfully."
            }

        endpoint = "/pg/v1/pay"
        
        # PhonePe Standard Payload
        payload_dict = {
            "merchantId": MERCHANT_ID,
            "merchantTransactionId": transaction_id,
            "merchantUserId": data.get("user_id"),
            "amount": amount_paise,
            "redirectUrl": "http://localhost:5173/app/billing",
            "redirectMode": "POST",
            "callbackUrl": "https://your-ngrok-url/api/payment/callback", # Usually injected dynamically from env
            "mobileNumber": data.get("mobile_number"),
            "paymentInstrument": {
                "type": "PAY_PAGE"
            }
        }
        
        # Convert Dictionary to Base64 JSON
        payload_json = json.dumps(payload_dict)
        payload_base64 = base64.b64encode(payload_json.encode('utf-8')).decode('utf-8')
        
        checksum = PhonePeService.generate_checksum(payload_base64, endpoint)
        
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": checksum
        }
        
        body = {"request": payload_base64}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{BASE_URL}{endpoint}", json=body, headers=headers)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get("success"):
                redirect_url = response_data["data"]["instrumentResponse"]["redirectInfo"]["url"]
                return {
                    "success": True,
                    "redirect_url": redirect_url,
                    "transaction_id": transaction_id,
                    "message": "Payment initiated successfully via PhonePe."
                }
            else:
                return {
                    "success": False,
                    "redirect_url": None,
                    "transaction_id": transaction_id,
                    "message": response_data.get("message", "Payment initiation failed.")
                }

    @staticmethod
    def verify_callback(payload_base64: str, x_verify: str) -> bool:
        """
        Validates the authenticity of the webhook notification.
        """
        if ENV == "development" and PHONEPE_SIMULATION:
            return True
            
        expected_checksum = PhonePeService.generate_checksum(payload_base64, "")
        return x_verify == expected_checksum

    @staticmethod
    async def check_status(merchant_transaction_id: str) -> Dict[str, Any]:
        """
        Queries the final transaction state natively via PhonePe API.
        """
        if ENV == "development" and PHONEPE_SIMULATION:
            return {
                "success": True,
                "status": "PAYMENT_SUCCESS",
                "transaction_id": merchant_transaction_id,
                "amount": 10000 
            }

        endpoint = f"/pg/v1/status/{MERCHANT_ID}/{merchant_transaction_id}"
        
        # PhonePe Status API Checksum formula: SHA256(Endpoint + Salt_Key) + "###" + Salt_Index
        # No payload involved
        string_to_hash = endpoint + SALT_KEY
        hashed_string = hashlib.sha256(string_to_hash.encode('utf-8')).hexdigest()
        checksum = f"{hashed_string}###{SALT_INDEX}"
        
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": checksum,
            "X-MERCHANT-ID": MERCHANT_ID
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}{endpoint}", headers=headers)
            data = response.json()
            
            return {
                "success": data.get("success", False),
                "status": data.get("code", "UNKNOWN"),
                "transaction_id": merchant_transaction_id,
                "amount": data.get("data", {}).get("amount")
            }
