from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class SSOLoginInput(BaseModel):
    email: EmailStr
    name: str
    sso_id: Optional[str] = None
    access_token: Optional[str] = None


class PlanResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float
    features: Optional[List[str]] = None

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: str
    sso_id: Optional[str] = None
    email: str
    name: str

    active_plan_id: Optional[int] = None
    subscription_status: str
    renewal_date: Optional[datetime] = None
    created_at: datetime
    plan: Optional[PlanResponse] = None

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None

class PurchaseResponse(BaseModel):
    id: str
    user_id: str
    plan_id: int
    whitenet_order_id: Optional[str] = None
    amount: float
    status: str
    checkout_token: Optional[str] = None
    created_at: datetime
    plan: Optional[PlanResponse] = None

    class Config:
        from_attributes = True

class CheckoutInitiateInput(BaseModel):
    plan_id: int

class CheckoutInitiateResponse(BaseModel):
    purchase_id: str
    checkout_url: str
    checkout_token: Optional[str] = None
    whitenet_order_id: Optional[str] = None
    mock_checkout: bool
