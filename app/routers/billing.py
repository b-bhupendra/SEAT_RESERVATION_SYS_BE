from fastapi import APIRouter, Request, HTTPException, status, Header
from typing import Dict, Any

from app.schemas.payment import PaymentInitiateRequest, PaymentResponse, StatusResponse
from app.services.phonepe import PhonePeService

router = APIRouter(prefix="/api/payment", tags=["Payment Integration"])

@router.post("/pay", response_model=PaymentResponse)
async def initiate_payment(data: PaymentInitiateRequest):
    """
    Endpoint for frontend to initiate a transaction.
    """
    response = await PhonePeService.initiate_payment(data.dict())
    
    if not response["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=response["message"]
        )
        
    return PaymentResponse(**response)

@router.post("/callback", status_code=status.HTTP_200_OK)
async def payment_webhook(request: Request, x_verify: str = Header(None, alias="X-VERIFY")):
    """
    Server-to-Server webhook endpoint called natively by PhonePe upon transaction completion.
    Must be exposed to the public internet.
    """
    if not x_verify:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Missing checksum header"
        )
        
    try:
        body = await request.json()
        payload_base64 = body.get("response")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid request payload"
        )
        
    if not payload_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Payload missing"
        )

    # 1. Verify authenticity of the callback
    is_valid = PhonePeService.verify_callback(payload_base64, x_verify)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid signature"
        )

    # 2. Extract transaction updates
    import base64
    import json
    
    try:
        decoded_bytes = base64.b64decode(payload_base64)
        response_data = json.loads(decoded_bytes.decode('utf-8'))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Malformed Base64 payload"
        )

    # At this point, the callback is authentic and decoded.
    # Here you would typically look up the bill by response_data['data']['merchantTransactionId']
    # and update the DB status (PAYMENT_SUCCESS, PAYMENT_ERROR, etc.)
    
    return {"status": "success", "message": "Callback processed"}

@router.get("/status/{transaction_id}", response_model=StatusResponse)
async def get_payment_status(transaction_id: str):
    """
    Endpoint for the frontend to poll the final status of a payment.
    Queries the PhonePe API to guarantee the single source of truth.
    """
    response = await PhonePeService.check_status(transaction_id)
    
    return StatusResponse(**response)
