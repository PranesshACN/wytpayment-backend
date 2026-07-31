from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.models import SubscriptionPlan
from app.schemas.schemas import PlanResponse

router = APIRouter(prefix="/api/plans", tags=["plans"])

@router.get("", response_model=List[PlanResponse])
def get_plans(db: Session = Depends(get_db)):
    plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.price).all()
    return plans

@router.post("/seed")
def seed_plans(db: Session = Depends(get_db)):
    # Clear existing to ensure clean seed
    db.query(SubscriptionPlan).delete()
    
    seeds = [
        SubscriptionPlan(
            id=1,
            name="Starter",
            description="Perfect for individuals testing out the SaaS ecosystem.",
            price=100.0,
            features=["Basic analytics", "Up to 5 integrations", "Email support", "Single user license"]
        ),
        SubscriptionPlan(
            id=2,
            name="Professional",
            description="Our most popular plan. Designed for small teams and developers.",
            price=500.0,
            features=["Advanced analytics", "Unlimited integrations", "24/7 Priority support", "Up to 5 user licenses", "API Access"]
        ),
        SubscriptionPlan(
            id=3,
            name="Enterprise",
            description="Fully customizable solution built for large corporate scale.",
            price=1000.0,
            features=["Custom reports", "Dedicated Account Manager", "SLA uptime agreement", "Unlimited users", "Whitelabel branding"]
        )
    ]
    
    for plan in seeds:
        db.add(plan)
    db.commit()
    return {"message": "Plans seeded successfully"}
