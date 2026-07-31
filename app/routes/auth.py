from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import UserCreate, UserLogin, SSOLoginInput, UserResponse, TokenResponse
from app.core import security

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

