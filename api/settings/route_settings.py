from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db_core import get_db
from .model_settings import DBSetting, Setting, SettingUpdate
from ..auth_user.dependencies import RoleChecker, PermissionChecker
from typing import Dict

router = APIRouter(prefix="/api", tags=["settings"])

ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff", "customer"]

@router.get("/settings", response_model=Dict[str, str])
def get_settings(db: Session = Depends(get_db)):
    """
    Returns system settings as a key-value dictionary.
    """
    # Ensure default settings are populated
    default_hold = db.query(DBSetting).filter(DBSetting.key == "seat_hold_duration_minutes").first()
    if not default_hold:
        default_hold = DBSetting(key="seat_hold_duration_minutes", value="15")
        db.add(default_hold)
        
    default_fine_enabled = db.query(DBSetting).filter(DBSetting.key == "enable_late_payment_fine").first()
    if not default_fine_enabled:
        default_fine_enabled = DBSetting(key="enable_late_payment_fine", value="false")
        db.add(default_fine_enabled)

    default_fine_amount = db.query(DBSetting).filter(DBSetting.key == "late_payment_fine_amount").first()
    if not default_fine_amount:
        default_fine_amount = DBSetting(key="late_payment_fine_amount", value="250")
        db.add(default_fine_amount)

    default_grace_bronze = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_bronze_days").first()
    if not default_grace_bronze:
        default_grace_bronze = DBSetting(key="loyalty_grace_bronze_days", value="2")
        db.add(default_grace_bronze)

    default_grace_silver = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_silver_days").first()
    if not default_grace_silver:
        default_grace_silver = DBSetting(key="loyalty_grace_silver_days", value="4")
        db.add(default_grace_silver)

    default_grace_gold = db.query(DBSetting).filter(DBSetting.key == "loyalty_grace_gold_days").first()
    if not default_grace_gold:
        default_grace_gold = DBSetting(key="loyalty_grace_gold_days", value="7")
        db.add(default_grace_gold)

    default_config_updating = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if not default_config_updating:
        default_config_updating = DBSetting(key="is_updating_config", value="false")
        db.add(default_config_updating)

    # Cash payment window defaults (hours the customer has to deliver cash)
    for key, val in [
        ("cash_payment_window_hours", "48"),        # default fallback for any tier
        ("cash_payment_bronze_hours", "24"),         # bronze customers: 24h
        ("cash_payment_silver_hours", "48"),         # silver customers: 48h
        ("cash_payment_gold_hours",   "72"),         # gold   customers: 72h
    ]:
        if not db.query(DBSetting).filter(DBSetting.key == key).first():
            db.add(DBSetting(key=key, value=val))

    db.commit()

    settings = db.query(DBSetting).all()
    return {s.key: s.value for s in settings}

from ..auth_user.dependencies import PermissionChecker
from pydantic import BaseModel

class LoyaltyGraceUpdateRequest(BaseModel):
    bronze_days: int
    silver_days: int
    gold_days: int

@router.post("/settings/loyalty-grace")
def update_loyalty_grace_settings(
    req: LoyaltyGraceUpdateRequest,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("manage_billing"))
):
    """
    Unified settings update route that validates:
    Bronze <= Silver <= Gold.
    Locks the database configuration state (is_updating_config = true)
    during updates to prevent concurrent transaction/payment fulfillment race conditions.
    """
    if not (req.bronze_days <= req.silver_days <= req.gold_days):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration error: Invalid grace days sequence (Bronze: {req.bronze_days}, Silver: {req.silver_days}, Gold: {req.gold_days}). Enforce: Bronze <= Silver <= Gold days."
        )

    lock_setting = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if not lock_setting:
        lock_setting = DBSetting(key="is_updating_config", value="true")
        db.add(lock_setting)
    else:
        lock_setting.value = "true"
    db.commit()

    try:
        for key, val in [
            ("loyalty_grace_bronze_days", str(req.bronze_days)),
            ("loyalty_grace_silver_days", str(req.silver_days)),
            ("loyalty_grace_gold_days", str(req.gold_days))
        ]:
            setting = db.query(DBSetting).filter(DBSetting.key == key).first()
            if not setting:
                db.add(DBSetting(key=key, value=val))
            else:
                setting.value = val
        db.commit()
    finally:
        lock_setting.value = "false"
        db.commit()

    return {"status": "success", "message": "Loyalty grace periods updated successfully."}

@router.post("/settings/system-lock", response_model=Dict[str, str])
def toggle_system_lock(
    update: SettingUpdate,
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(ADMIN_MGR))
):
    """
    Dedicated endpoint to toggle the is_updating_config maintenance lock.
    Uses RoleChecker (not PermissionChecker) to avoid the circular deadlock
    where releasing the lock would itself be blocked by the lock check.
    """
    if update.value not in ("true", "false"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Value must be 'true' or 'false'."
        )
    setting = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if not setting:
        setting = DBSetting(key="is_updating_config", value=update.value)
        db.add(setting)
    else:
        setting.value = update.value
    db.commit()
    db.refresh(setting)
    return {setting.key: setting.value}

@router.post("/settings/{key}", response_model=Dict[str, str])
def update_setting(
    key: str,
    update: SettingUpdate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("manage_billing"))
):
    """
    Updates or inserts a system setting key (ability-checked).
    The is_updating_config key is reserved — use /settings/system-lock instead.
    """
    if key == "is_updating_config":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /api/settings/system-lock to toggle the maintenance lock."
        )

    if key == "seat_hold_duration_minutes":
        try:
            val = int(update.value)
            if val <= 0 or val > 60:
                raise ValueError()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration error: Seat hold duration must be a positive integer between 1 and 60 minutes."
            )

    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    if not setting:
        setting = DBSetting(key=key, value=update.value)
        db.add(setting)
    else:
        setting.value = update.value

    db.commit()
    db.refresh(setting)
    return {setting.key: setting.value}
