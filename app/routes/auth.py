import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    UserCreate,
    UserLogin,
    SSOLoginInput,
    SSOExchangeInput,
    ForgotPasswordInput,
    ResetPasswordInput,
    RefreshTokenInput,
    UserResponse,
    TokenResponse
)
from app.core import security
from app.core import config
from app.services.wytnet_auth import wytnet_auth_service

logger = logging.getLogger("auth_routes")

router = APIRouter(prefix="/api/auth", tags=["auth"])

def _upsert_wytnet_user(db: Session, sub: str, email: str, name: str, phone: Optional[str] = None) -> User:
    """
    Helper to sync or update a user record keyed by WytNet's canonical stable subject ID: sub.
    """
    user = db.query(User).filter(
        (User.id == sub) | (User.sub == sub) | (User.email == email)
    ).first()

    if not user:
        user = User(
            id=sub,
            sub=sub,
            sso_id=sub,
            email=email,
            name=name or email.split("@")[0],
            phone=phone
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new local user record for WytNet user {sub} ({email})")
    else:
        # Update user attributes if changed
        updated = False
        if user.id != sub:
            # If the user existed under legacy ID, assign sub
            user.sub = sub
            updated = True
        if name and user.name != name:
            user.name = name
            updated = True
        if phone and user.phone != phone:
            user.phone = phone
            updated = True
        if updated:
            db.commit()
            db.refresh(user)

    return user

@router.post("/register", response_model=UserResponse)
def register_user(data: UserCreate, db: Session = Depends(get_db)):
    """
    User Registration: Forwarded centrally to WytNet.
    Local database stores no passwords or password hashes.
    """
    res = wytnet_auth_service.register_user(
        name=data.name,
        email=data.email,
        password=data.password,
        phone=data.phone
    )

    # WytNet returns user details or user object
    user_data = res.get("user") or res
    sub = user_data.get("sub") or user_data.get("id") or f"wn_usr_{data.email.replace('@', '_').replace('.', '_')}"
    name = user_data.get("name") or data.name
    email = user_data.get("email") or data.email

    user = _upsert_wytnet_user(db, sub=sub, email=email, name=name, phone=data.phone)
    return user

@router.post("/login", response_model=TokenResponse)
def login_user(data: UserLogin, response: Response, db: Session = Depends(get_db)):
    """
    Flow A: Direct Email + Password Authentication.
    Submits credentials securely to WytNet auth-layer.
    Sets secure HttpOnly session cookies and returns session tokens.
    """
    auth_res = wytnet_auth_service.authenticate_direct(data.email, data.password)

    access_token = auth_res.get("access_token")
    refresh_token = auth_res.get("refresh_token")
    id_token = auth_res.get("id_token")
    token_type = auth_res.get("token_type", "Bearer")
    expires_in = auth_res.get("expires_in", 3600)

    # Extract user identity returned by WytNet
    user_info = auth_res.get("user") or {}
    sub = user_info.get("sub") or user_info.get("id")
    email = user_info.get("email") or data.email
    name = user_info.get("name") or email.split("@")[0]

    if not sub:
        # Fallback to inspecting token payload
        try:
            verified = wytnet_auth_service.verify_token(access_token)
            sub = verified.get("sub") or f"wn_usr_{email}"
            name = verified.get("name") or name
        except Exception:
            sub = f"wn_usr_{email}"

    user = _upsert_wytnet_user(db, sub=sub, email=email, name=name)

    # Store session tokens in secure, HttpOnly, SameSite=Lax cookies
    security.set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)

    return {
        "access_token": access_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "user": user
    }

@router.post("/sso-exchange", response_model=TokenResponse)
def sso_exchange_token(data: SSOExchangeInput, response: Response, db: Session = Depends(get_db)):
    """
    Flow B: OAuth 2.0 PKCE Code Exchange via backend.
    Exchanges authorization code with WytNet IdP server-to-server.
    Protects client_secret and configures HttpOnly session cookies.
    """
    token_data = wytnet_auth_service.exchange_authorization_code(
        code=data.code,
        code_verifier=data.code_verifier,
        redirect_uri=data.redirect_uri
    )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    id_token = token_data.get("id_token")
    expires_in = token_data.get("expires_in", 3600)
    token_type = token_data.get("token_type", "Bearer")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WytNet OAuth exchange returned no access token"
        )

    # Decode identity from id_token or access_token via WytNet verification
    token_to_verify = id_token or access_token
    payload = wytnet_auth_service.verify_token(token_to_verify)

    sub = payload.get("sub") or payload.get("user_id") or token_data.get("user", {}).get("sub")
    email = payload.get("email") or token_data.get("user", {}).get("email") or f"{sub}@wytpass.usr"
    name = payload.get("name") or token_data.get("user", {}).get("name") or email.split("@")[0]

    user = _upsert_wytnet_user(db, sub=sub, email=email, name=name)

    # Set secure HttpOnly cookies
    security.set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)

    return {
        "access_token": access_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "user": user
    }

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordInput):
    """
    Forgot Password: Request password reset token through WytNet.
    """
    return wytnet_auth_service.forgot_password(email=data.email)

@router.post("/reset-password")
def reset_password(data: ResetPasswordInput):
    """
    Reset Password: Submit new password using reset token through WytNet.
    """
    return wytnet_auth_service.reset_password(
        token=data.token,
        new_password=data.new_password,
        confirm_password=data.confirm_password
    )

@router.post("/refresh")
def refresh_session_token(
    request: Request,
    response: Response,
    data: Optional[RefreshTokenInput] = None
):
    """
    OAuth 2.0 Token Refresh.
    Reads refresh token from request body or HttpOnly cookie.
    """
    refresh_token = (data.refresh_token if data else None) or request.cookies.get("wytpass_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    tokens = wytnet_auth_service.refresh_access_token(refresh_token)
    new_access_token = tokens.get("access_token")
    new_refresh_token = tokens.get("refresh_token") or refresh_token

    if new_access_token:
        security.set_auth_cookies(response, access_token=new_access_token, refresh_token=new_refresh_token)

    return tokens

@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(security.get_current_user)
):
    """
    Revokes access token on WytNet and clears local HttpOnly session cookies.
    """
    token = request.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "").strip()
    else:
        token = request.cookies.get("wytpass_access_token")

    if token:
        wytnet_auth_service.revoke_token(token)

    security.clear_auth_cookies(response)
    return {"status": "logged_out", "message": "Successfully logged out from WytPass"}

@router.post("/sso-login", response_model=TokenResponse)
def sso_login_user(data: SSOLoginInput, response: Response, db: Session = Depends(get_db)):
    """
    Compatibility SSO endpoint for legacy callers.
    """
    sub = data.sso_id or f"wn_usr_{data.email.replace('@', '_')}"
    user = _upsert_wytnet_user(db, sub=sub, email=data.email, name=data.name)

    token = data.access_token or f"mock_token_{sub}"
    security.set_auth_cookies(response, access_token=token)

    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "user": user
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(security.get_current_user)):
    """Returns currently authenticated user profile."""
    return current_user
