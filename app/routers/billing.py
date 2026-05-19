from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from typing import Dict, Any
from datetime import datetime, timedelta
import uuid

from app.schemas.payment import PaymentInitiateRequest, PaymentResponse, StatusResponse
from app.services.phonepe import PhonePeService

# Fulfillment imports
from api.db_core import SessionLocal, get_db
from sqlalchemy.orm import Session
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation
from api.billing.model_bills import DBBill, DBTransaction

router = APIRouter(prefix="/api/payment", tags=["Payment Integration"])

TRANSACTION_USER_MAP = {}

def fulfill_transaction_logic(transaction_id: str, db: Session) -> dict:
    """
    Idempotent helper to fulfill a payment. 
    Uses row-level locking to prevent concurrency issues, and flags processed transactions.
    """
    # 1. Look up the transaction in DB with row-level locking
    txn = db.query(DBTransaction).filter(DBTransaction.transaction_id == transaction_id).with_for_update().first()
    
    customer_id = None
    if txn:
        customer_id = txn.customer_id
        if txn.processed:
            print(f"DEBUG: Transaction {transaction_id} is already processed. Skipping fulfillment.")
            return {"status": "already_processed", "customer_id": customer_id}
    else:
        # Fallback to TRANSACTION_USER_MAP for compatibility with legacy tests
        legacy_cust_id = TRANSACTION_USER_MAP.get(transaction_id)
        if legacy_cust_id:
            customer_id = uuid.UUID(legacy_cust_id)
            # Create a DBTransaction record so that subsequent calls are idempotent!
            txn = DBTransaction(
                transaction_id=transaction_id,
                customer_id=customer_id,
                amount=1500.0, # default/mock amount
                status="SUCCESS",
                processed=False
            )
            db.add(txn)
            db.flush()
            # Lock the newly created transaction
            txn = db.query(DBTransaction).filter(DBTransaction.transaction_id == transaction_id).with_for_update().first()
            
    if not customer_id:
        # Fallback to the latest active customer if no mapping found (legacy behavior, but discouraged)
        customer = db.query(DBCustomer).filter(DBCustomer.status == "active").order_by(DBCustomer.first_contact.desc()).first()
        if customer:
            customer_id = customer.id
            
    if not customer_id:
        print(f"Fulfillment Warning: No customer could be mapped to transaction {transaction_id}")
        return {"status": "no_customer_found"}
        
    customer = db.query(DBCustomer).filter(DBCustomer.id == customer_id).first()
    if not customer:
        print(f"Fulfillment Warning: Customer {customer_id} not found in database")
        return {"status": "customer_not_found"}

    try:
        # Calculate loyalty tier & grace days
        from api.reservations.loyalty import calculate_loyalty_and_grace, calculate_fine_and_total
        tier, grace_days = calculate_loyalty_and_grace(db, customer.id)
        
        # Check for existing reservation (paid or pending)
        existing = db.query(DBReservation).filter(DBReservation.customer_id == customer.id).filter(DBReservation.status.in_(["paid", "pending"])).first()
        
        # If none found, check if they have a recently expired reservation that is still in grace period
        if not existing:
            expired_res = db.query(DBReservation).filter(
                DBReservation.customer_id == customer.id,
                DBReservation.status == "paid",
                DBReservation.end_date < datetime.utcnow()
            ).order_by(DBReservation.end_date.desc()).first()
            
            if expired_res:
                expiry_deadline = expired_res.end_date + timedelta(days=grace_days)
                if datetime.utcnow() <= expiry_deadline:
                    existing = expired_res
                    print(f"DEBUG: Found expired reservation {existing.seat_number} in grace period for customer {customer.email}")

        from api.reservations.route_reservations import generate_sequential_seat_number
        
        # Check for Late Payment Fine adjustment
        fine_applied = 0.0
        if existing and existing.status == "paid" and existing.end_date and datetime.utcnow() > existing.end_date:
            # It was expired, so late payment fine applies!
            fine_applied, _ = calculate_fine_and_total(db, customer.id, existing.amount or 1500.0, existing.end_date)
            print(f"DEBUG: Late Payment Fine of ₹{fine_applied} applied for customer {customer.email}")

        if not existing:
            # Create new reservation
            seat_num = generate_sequential_seat_number(db, customer.organization, customer.sub_organization)
            new_res = DBReservation(
                customer_id=customer.id,
                seat_number=seat_num,
                subsection=customer.sub_organization or "Premium Zone",
                organization=customer.organization,
                sub_organization=customer.sub_organization,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                status="paid"
            )
            db.add(new_res)
            print(f"Fulfillment: Created fresh reservation for {customer.email}")
        else:
            # Renewal or pending hold fulfillment!
            seat_num = existing.seat_number
            
            # COLLISION CHECK & RESOLUTION!
            collision_reservations = db.query(DBReservation).filter(
                DBReservation.seat_number == seat_num,
                DBReservation.organization == existing.organization,
                DBReservation.sub_organization == existing.sub_organization,
                DBReservation.status.in_(["paid", "pending"]),
                DBReservation.customer_id != customer.id
            ).all()
            
            for coll_res in collision_reservations:
                print(f"COLLISION: Resolving seat {seat_num} collision. New guy {coll_res.customer_id} is refunded, loyal customer {customer.id} retains.")
                coll_res.status = "cancelled"
                
                # Set their paid bills to refunded
                from api.billing.model_bills import DBBill
                new_guy_bills = db.query(DBBill).filter(
                    DBBill.customer_id == coll_res.customer_id,
                    DBBill.status.in_(["paid", "pending"])
                ).all()
                for bill in new_guy_bills:
                    bill.status = "refunded"
                    
                # Query alternative vacant seats in same sub-organization for the cancelled customer
                from api.reservations.model_seats import DBSeat
                all_seats = db.query(DBSeat).filter(
                    DBSeat.organization == existing.organization,
                    DBSeat.sub_organization == existing.sub_organization
                ).all()
                
                vacant_alternatives = []
                for seat in all_seats:
                    active_res = db.query(DBReservation).filter(
                        DBReservation.seat_number == seat.seat_number,
                        DBReservation.organization == seat.organization,
                        DBReservation.sub_organization == seat.sub_organization,
                        DBReservation.status.in_(["paid", "pending"])
                    ).first()
                    if not active_res:
                        vacant_alternatives.append(seat.seat_number)
                        if len(vacant_alternatives) >= 15:
                            break
                            
                alt_text = ""
                if vacant_alternatives:
                    alt_text = f" We highly recommend booking one of these available alternative vacant seats in the same zone: {', '.join(vacant_alternatives)}."

                # Send priority refund notification to new customer
                from api.notifications.model_notifications import DBNotification
                refund_notif = DBNotification(
                    customer_id=coll_res.customer_id,
                    message=f"Your reservation on seat {seat_num} was refunded and cancelled because a priority loyal member renewed within their grace period. A full refund has been initiated.{alt_text}",
                    sent_at=datetime.utcnow(),
                    is_read=False
                )
                db.add(refund_notif)
            
            # Update existing loyal customer's reservation
            existing.status = "paid"
            # If renewing an expired seat, extend 30 days from now. Otherwise, add 30 days to end_date.
            if existing.end_date and existing.end_date > datetime.utcnow():
                existing.end_date = existing.end_date + timedelta(days=30)
            else:
                existing.end_date = datetime.utcnow() + timedelta(days=30)
            existing.start_date = datetime.utcnow()
            
            # Update matching pending bill to paid
            from api.billing.model_bills import DBBill
            matching_bill = db.query(DBBill).filter(
                DBBill.customer_id == customer.id,
                DBBill.status == "pending"
            ).order_by(DBBill.due_date.desc()).first()
            
            if matching_bill:
                matching_bill.status = "paid"
                matching_bill.pay_date = datetime.utcnow()
                if fine_applied > 0:
                    matching_bill.amount += fine_applied

            # Notify loyal customer of priority activation
            from api.notifications.model_notifications import DBNotification
            success_notif = DBNotification(
                customer_id=customer.id,
                message=f"Priority seat protection activated! Your late seat renewal on {seat_num} was successful. Welcome back!",
                sent_at=datetime.utcnow(),
                is_read=False
            )
            db.add(success_notif)
            
        # Update transaction status to SUCCESS and processed to True
        if txn:
            txn.status = "SUCCESS"
            txn.processed = True
        
        db.commit()
        print(f"Fulfillment: Successfully processed transaction {transaction_id} for {customer.email}")
        return {"status": "fulfilled", "customer_id": customer.id}
        
    except Exception as e:
        db.rollback()
        print(f"Fulfillment Error for transaction {transaction_id}: {e}")
        raise e

@router.post("/pay", response_model=PaymentResponse)
async def initiate_payment(data: PaymentInitiateRequest, db: Session = Depends(get_db)):
    """
    Endpoint for frontend to initiate a transaction.
    """
    response = await PhonePeService.initiate_payment(data.dict())
    
    if not response["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=response["message"]
        )
        
    TRANSACTION_USER_MAP[response["transaction_id"]] = data.user_id
    
    # Save the transaction in the database
    try:
        txn = DBTransaction(
            transaction_id=response["transaction_id"],
            customer_id=uuid.UUID(data.user_id),
            amount=data.amount,
            status="PENDING",
            processed=False
        )
        db.add(txn)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error persisting transaction: {e}")
        
    return PaymentResponse(**response)

@router.post("/callback", status_code=status.HTTP_200_OK)
async def payment_webhook(request: Request, x_verify: str = Header(None, alias="X-VERIFY"), db: Session = Depends(get_db)):
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

    # Run fulfillment logic on SUCCESS callback
    txn_data = response_data.get("data", {})
    merchant_txn_id = txn_data.get("merchantTransactionId")
    response_code = response_data.get("code")
    
    if merchant_txn_id:
        if response_code == "PAYMENT_SUCCESS":
            fulfill_transaction_logic(merchant_txn_id, db)
        elif response_code in ["PAYMENT_ERROR", "PAYMENT_DECLINED", "TIMED_OUT"]:
            # Update status in DB
            txn = db.query(DBTransaction).filter(DBTransaction.transaction_id == merchant_txn_id).with_for_update().first()
            if txn:
                txn.status = response_code
                db.commit()
    
    return {"status": "success", "message": "Callback processed"}

@router.get("/status/{transaction_id}", response_model=StatusResponse)
async def get_payment_status(transaction_id: str, db: Session = Depends(get_db)):
    """
    Endpoint for the frontend to poll the final status of a payment.
    Queries the PhonePe API to guarantee the single source of truth.
    Also fulfills the reservation if payment is successful (Simulation/Demo Mode).
    Handles dynamic loyalty grace periods, late fines, and collision priority resolutions.
    """
    from api.settings.model_settings import DBSetting
    from fastapi import status as status_codes
    config_lock = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if config_lock and config_lock.value == "true":
        raise HTTPException(
            status_code=status_codes.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is temporarily suspended due to administrative configuration updates. Please retry in a few seconds."
        )

    response = await PhonePeService.check_status(transaction_id)
    
    # Fulfillment Logic for Demo/Test
    print(f"DEBUG: Status check for {transaction_id}, response: {response['status']}")
    if response["success"] and response["status"] == "PAYMENT_SUCCESS":
        try:
            fulfill_transaction_logic(transaction_id, db)
        except Exception as e:
            print(f"Fulfillment Error: {e}")
    elif response["status"] in ["PAYMENT_ERROR", "PAYMENT_DECLINED", "TIMED_OUT"]:
        # Update status in DB
        txn = db.query(DBTransaction).filter(DBTransaction.transaction_id == transaction_id).with_for_update().first()
        if txn:
            txn.status = response["status"]
            db.commit()
            
    return StatusResponse(**response)
