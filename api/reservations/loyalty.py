from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import Session
from ..billing.model_bills import DBBill
from ..customers.model_customers import DBCustomer
from ..settings.model_settings import DBSetting

def calculate_loyalty_and_grace(db: Session, customer_id: uuid.UUID) -> tuple[str, int]:
    """
    Computes a customer's Loyalty Tier and Grace Period in days dynamically from admin settings:
    - Gold Tier: >= 5 successful payments -> loyalty_grace_gold_days grace period.
    - Silver Tier: 2-4 successful payments OR (>= 1 payment AND account age >= 30 days) -> loyalty_grace_silver_days.
    - Bronze Tier: Otherwise -> loyalty_grace_bronze_days.
    """
    bronze_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_bronze_days").first()
    silver_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_silver_days").first()
    gold_set = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_gold_days").first()

    bronze_days = int(bronze_set.value) if (bronze_set and bronze_set.value.isdigit()) else 2
    silver_days = int(silver_set.value) if (silver_set and silver_set.value.isdigit()) else 4
    gold_days = int(gold_set.value) if (gold_set and gold_set.value.isdigit()) else 7

    customer = db.query(DBCustomer).filter(DBCustomer.id == customer_id).first()
    if not customer:
        return "Bronze", bronze_days

    # Count successfully completed payments
    payments_count = db.query(DBBill).filter(
        DBBill.customer_id == customer_id,
        DBBill.status == "paid"
    ).count()

    # Determine account age
    is_one_month_old = False
    if customer.first_contact:
        age = datetime.utcnow() - customer.first_contact
        if age.days >= 30:
            is_one_month_old = True

    if payments_count >= 5:
        return "Gold", gold_days
    elif payments_count >= 2 or (payments_count >= 1 and is_one_month_old):
        return "Silver", silver_days
    else:
        return "Bronze", bronze_days

def calculate_fine_and_total(db: Session, customer_id: uuid.UUID, base_amount: float, plan_expiry: datetime) -> tuple[float, float]:
    """
    Calculates late payment fine if the customer is renewing past their expiry date and fine is enabled.
    Returns: (fine_amount, total_amount)
    """
    # Check if late payment fine is enabled
    fine_enabled_setting = db.query(DBSetting).filter(DBSetting.key == "enable_late_payment_fine").first()
    fine_enabled = fine_enabled_setting and fine_enabled_setting.value.lower() == "true"

    if fine_enabled and datetime.utcnow() > plan_expiry:
        fine_amount_setting = db.query(DBSetting).filter(DBSetting.key == "late_payment_fine_amount").first()
        fine_amount = 250.0
        if fine_amount_setting:
            try:
                fine_amount = float(fine_amount_setting.value)
            except ValueError:
                pass
        return fine_amount, base_amount + fine_amount

    return 0.0, base_amount
