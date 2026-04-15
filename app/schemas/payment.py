from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PaymentInitiateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount in INR")
    user_id: str
    mobile_number: str = Field(..., min_length=10, max_length=15)
    description: Optional[str] = "Lumina Pro Reservation"

class PaymentResponse(BaseModel):
    success: bool
    redirect_url: Optional[str] = None
    transaction_id: str
    message: str

class CallbackResponse(BaseModel):
    success: bool
    code: str
    message: str
    data: Optional[Dict[str, Any]] = None

class StatusResponse(BaseModel):
    success: bool
    status: str
    transaction_id: str
    amount: Optional[int] = None
