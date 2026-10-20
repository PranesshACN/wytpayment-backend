from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordInput(BaseModel):
    email: EmailStr

class ResetPasswordInput(BaseModel):
    token: str
    new_password: str
    confirm_password: str

class RefreshTokenInput(BaseModel):
    refresh_token: Optional[str] = None

class SSOLoginInput(BaseModel):
    email: EmailStr
    name: str
    sso_id: Optional[str] = None
    access_token: Optional[str] = None

class SSOExchangeInput(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


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
    sub: Optional[str] = None
    sso_id: Optional[str] = None
    email: str
    name: str
    phone: Optional[str] = None

    active_plan_id: Optional[int] = None
    subscription_status: str
    renewal_date: Optional[datetime] = None
    created_at: datetime
    plan: Optional[PlanResponse] = None

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = 3600
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    user: UserResponse

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None

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
