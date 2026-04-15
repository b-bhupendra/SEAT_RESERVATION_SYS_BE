import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def notify_supabase(user_id: str, message: str):
    """
    Utility to push a real-time notification to Supabase.
    """
    if not supabase_client:
        return None
    
    try:
        response = supabase_client.table("notifications").insert({
            "user_id": user_id,
            "message": message,
            "is_read": False
        }).execute()
        return response.data
    except Exception as e:
        print(f"Supabase broadcast failed: {e}")
        return None
