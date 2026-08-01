from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
import requests as http_requests
import logging
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import UserCreate, UserLogin, SSOLoginInput, UserResponse, TokenResponse
from app.core import security
from app.core import config

logger = logging.getLogger("demo_saas_app")

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register_user(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    new_user = User(
        email=data.email,
        name=data.name,
        hashed_password=security.get_password_hash(data.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=TokenResponse)
def login_user(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not security.verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    token = security.create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/sso-login", response_model=TokenResponse)
def sso_login_user(data: SSOLoginInput, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        # Register user on first SSO login
        user = User(
            email=data.email,
            name=data.name or data.email.split("@")[0],
            hashed_password=security.get_password_hash(str(uuid.uuid4())),
            sso_id=data.sso_id
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if data.sso_id and user.sso_id != data.sso_id:
            user.sso_id = data.sso_id
            db.commit()
            db.refresh(user)

    
    token = security.create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(security.get_current_user)):
    return current_user


from pydantic import BaseModel

class SSOExchangeInput(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str

@router.post("/sso-exchange")
def sso_exchange_token(data: SSOExchangeInput):
    """
    Server-side proxy for WhitePass OAuth token exchange.
    The frontend sends the authorization code here, and this endpoint
    exchanges it with the WhitePass server (server-to-server, no CORS).
    """
    token_url = config.WHITEPASS_TOKEN_URL
    if not token_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WHITEPASS_TOKEN_URL not configured on server"
        )

    payload = {
        "grant_type": "authorization_code",
        "code": data.code,
        "client_id": config.WHITEPASS_CLIENT_ID,
        "client_secret": config.WHITEPASS_CLIENT_SECRET,
        "code_verifier": data.code_verifier,
        "redirect_uri": data.redirect_uri,
    }

    try:
        resp = http_requests.post(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except http_requests.exceptions.RequestException as e:
        logger.error(f"WhitePass token exchange network error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach WhitePass OAuth server: {str(e)}"
        )

    if not resp.ok:
        logger.error(f"WhitePass token exchange failed: {resp.status_code} {resp.text}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"WhitePass token exchange failed: {resp.text}"
        )

    return resp.json()
