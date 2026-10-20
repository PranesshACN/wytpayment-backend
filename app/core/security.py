import logging
from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core import config
from app.db.session import get_db
from app.models.models import User
from app.services.wytnet_auth import wytnet_auth_service

logger = logging.getLogger("app_security")

# OAuth2 bearer token scheme (auto_error=False to allow falling back to cookie)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def set_auth_cookies(response: Response, access_token: str, refresh_token: Optional[str] = None):
    """
    Stores session tokens in secure, HttpOnly, SameSite=Lax cookies.
    """
    response.set_cookie(
        key="wytpass_access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production (HTTPS)
        max_age=3600,
        path="/"
    )
    if refresh_token:
        response.set_cookie(
            key="wytpass_refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=30 * 24 * 3600,
            path="/"
        )

def clear_auth_cookies(response: Response):
    """
    Clears local session cookies on logout.
    """
    response.delete_cookie(key="wytpass_access_token", path="/")
    response.delete_cookie(key="wytpass_refresh_token", path="/")

async def get_current_user(
    request: Request,
    token_from_header: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Validates token from Authorization header or HttpOnly cookie using WytNet IdP.
    Syncs the canonical WytNet subject identifier (wn_usr_<uuid>) with the local user database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials with WytNet Identity Provider",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Extract token from header OR cookie
    token = token_from_header or request.cookies.get("wytpass_access_token")
    if not token:
        raise credentials_exception

    # 2. Delegate validation to WytNet (JWKS signature verification / Introspection)
    try:
        payload = wytnet_auth_service.verify_token(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise credentials_exception

    user_sub = payload.get("sub") or payload.get("user_id") or payload.get("id")
    if not user_sub:
        raise credentials_exception

    email = payload.get("email") or f"{user_sub}@wytpass.usr"
    name = payload.get("name") or payload.get("preferred_username") or email.split("@")[0]

    # 3. Synchronize user record with database using canonical WytNet 'sub' as primary key
    user = db.query(User).filter(
        (User.id == user_sub) | (User.sub == user_sub) | (User.email == email)
    ).first()

    if user is None:
        # First-time sync for WytNet authenticated user
        user = User(
            id=user_sub,
            sub=user_sub,
            sso_id=user_sub,
            email=email,
            name=name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Synchronized new user from WytNet with sub '{user_sub}'")
    else:
        # Ensure subject identifier is up-to-date
        updated = False
        if not user.sub or user.sub != user_sub:
            user.sub = user_sub
            updated = True
        if not user.sso_id:
            user.sso_id = user_sub
            updated = True
        if updated:
            db.commit()
            db.refresh(user)

    return user
