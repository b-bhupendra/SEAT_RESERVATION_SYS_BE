import os
import base64
import uuid
import mimetypes
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

def upload_base64_to_supabase(base64_string: str, folder: str = "uploads") -> str:
    """
    Decodes a base64 string (data:image/png;base64,iVBOR...) and uploads it to Supabase Storage.
    Returns the public URL of the uploaded file.
    """
    if not supabase_client or not base64_string:
        return base64_string # Fallback to base64 if no supabase client
    
    try:
        # Extract MIME type and pure base64 data
        if "base64," in base64_string:
            header, data = base64_string.split("base64,", 1)
            mime_type = header.split(":")[1].split(";")[0]
        else:
            data = base64_string
            mime_type = "application/octet-stream"

        extension = mimetypes.guess_extension(mime_type) or ".bin"
        file_bytes = base64.b64decode(data)
        
        filename = f"{folder}/{uuid.uuid4()}{extension}"
        
        supabase_client.storage.from_("customer-documents").upload(
            file=file_bytes,
            path=filename,
            file_options={"content-type": mime_type}
        )
        
        public_url = supabase_client.storage.from_("customer-documents").get_public_url(filename)
        return public_url
    except Exception as e:
        print(f"Supabase storage upload failed: {e}")
        return base64_string # Fallback to returning raw base64 if it fails
