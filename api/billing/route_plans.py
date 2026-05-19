from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_plans as schemas
from ..auth_user.dependencies import RoleChecker
from typing import List
import uuid

router = APIRouter(prefix="/api", tags=["plans"])

# Permissions
ADMIN_MGR = ["admin", "manager"]

@router.get("/plans", response_model=List[schemas.Plan])
def get_plans(db: Session = Depends(get_db)):
    """Public endpoint to fetch available subscription plans"""
    return db.query(schemas.DBPlan).all()

@router.post("/plans", response_model=schemas.Plan)
def create_plan(plan: schemas.PlanBase, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    """Admin endpoint to create a new plan"""
    db_plan = schemas.DBPlan(**plan.dict())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan

@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    """Admin endpoint to delete a plan"""
    db_plan = db.query(schemas.DBPlan).filter(schemas.DBPlan.id == plan_id).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    db.delete(db_plan)
    db.commit()
    return {"status": "deleted"}
