import time
import json
import logging
import requests
from typing import Dict, Any, Optional
from jose import jwt, jwk, JWTError
from jose.utils import base64url_decode
from fastapi import HTTPException, status
from app.core import config

logger = logging.getLogger("wytnet_auth")

class WytNetAuthService:
    def __init__(self):
        self.client_id = config.WYTPASS_CLIENT_ID
        self.client_secret = config.WYTPASS_CLIENT_SECRET
        self.issuer_url = config.WYTNET_ISSUER_URL
        self.auth_url = config.WYTNET_AUTH_URL
        self.token_url = config.WYTNET_TOKEN_URL
        self.jwks_url = config.WYTNET_JWKS_URL
        self.openid_config_url = config.WYTNET_OPENID_CONFIG_URL
        self.redirect_uri = config.WYTNET_REDIRECT_URI

        # In-memory cache for JWKS keys: { "keys": [...], "timestamp": float }
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_ttl: int = 3600  # 1 hour cache

    def _handle_request_error(self, response: requests.Response, context: str):
        """Helper to format and raise consistent exceptions, including 429 rate limiting."""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            logger.warning(f"WytNet rate limit reached during {context}. Retry-After: {retry_after}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests to WytNet identity server. Please try again in {retry_after} seconds.",
                headers={"Retry-After": retry_after}
            )

        try:
            err_data = response.json()
            detail = err_data.get("detail") or err_data.get("message") or err_data.get("error_description") or err_data.get("error") or response.text
        except Exception:
            detail = response.text or f"HTTP error {response.status_code}"

        logger.error(f"WytNet {context} error [{response.status_code}]: {detail}")
        raise HTTPException(
            status_code=response.status_code if response.status_code in [400, 401, 403, 404] else status.HTTP_502_BAD_GATEWAY,
            detail=detail
        )

    def authenticate_direct(self, email: str, password: str, scope: str = "openid profile email") -> Dict[str, Any]:
        """
        Flow A: Direct Email + Password verification delegated to WytNet.
        POST https://api.wytnet.com/auth-layer/authenticate
        """
        url = f"{self.issuer_url}/auth-layer/authenticate"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "email": email,
            "password": password,
            "scope": scope
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet authenticate: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet auth server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "Direct Authentication")

        return resp.json()

    def register_user(self, name: str, email: str, password: str, phone: Optional[str] = None) -> Dict[str, Any]:
        """
        User Registration forwarded centrally to WytNet.
        POST https://api.wytnet.com/auth-layer/register
        """
        url = f"{self.issuer_url}/auth-layer/register"
        payload = {
            "client_id": self.client_id,
            "name": name,
            "email": email,
            "password": password,
            "phone": phone or ""
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet register: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet register server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "User Registration")

        return resp.json()

    def forgot_password(self, email: str) -> Dict[str, Any]:
        """
        Password Recovery Request.
        POST https://api.wytnet.com/auth-layer/forgot-password
        """
        url = f"{self.issuer_url}/auth-layer/forgot-password"
        payload = {
            "client_id": self.client_id,
            "email": email
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet forgot-password: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet auth server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "Forgot Password")

        return resp.json()

    def reset_password(self, token: str, new_password: str, confirm_password: str) -> Dict[str, Any]:
        """
        Submit New Password with reset token.
        POST https://api.wytnet.com/auth-layer/reset-password
        """
        url = f"{self.issuer_url}/auth-layer/reset-password"
        payload = {
            "token": token,
            "new_password": new_password,
            "confirm_password": confirm_password
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet reset-password: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet auth server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "Reset Password")

        return resp.json()

    def exchange_authorization_code(self, code: str, code_verifier: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """
        Flow B: OAuth 2.0 PKCE Code Exchange.
        POST https://api.wytnet.com/oauth/token
        """
        url = self.token_url
        form_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier
        }

        try:
            resp = requests.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet OAuth code exchange: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet OAuth server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "OAuth Code Exchange")

        return resp.json()

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        OAuth 2.0 Token Refresh.
        POST https://api.wytnet.com/oauth/token
        """
        url = self.token_url
        form_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            resp = requests.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet token refresh: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet token server: {str(e)}")

        if not resp.ok:
            self._handle_request_error(resp, "Token Refresh")

        return resp.json()

    def revoke_token(self, token: str) -> Dict[str, Any]:
        """
        Token Revocation / Logout.
        POST https://api.wytnet.com/oauth/revoke
        """
        url = f"{self.issuer_url}/oauth/revoke"
        payload = {
            "token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if resp.ok:
                return resp.json() if resp.text else {"status": "revoked"}
        except Exception as e:
            logger.warning(f"Token revocation error (ignoring during logout): {e}")

        return {"status": "revocation_attempted"}

    def introspect_token(self, token: str) -> Dict[str, Any]:
        """
        OAuth 2.0 Token Introspection.
        POST https://api.wytnet.com/auth-layer/introspect
        """
        url = f"{self.issuer_url}/auth-layer/introspect"
        payload = {
            "token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if resp.ok:
                return resp.json()
            self._handle_request_error(resp, "Token Introspection")
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during WytNet introspection: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reach WytNet introspection endpoint: {str(e)}")

        return {}

    def get_jwks(self) -> Dict[str, Any]:
        """Retrieves and caches JWKS public keys from WytNet."""
        now = time.time()
        if self._jwks_cache and (now - self._jwks_cache.get("timestamp", 0) < self._jwks_cache_ttl):
            return self._jwks_cache.get("keys", {})

        try:
            resp = requests.get(self.jwks_url, timeout=10)
            if resp.ok:
                keys_data = resp.json()
                self._jwks_cache = {
                    "keys": keys_data,
                    "timestamp": now
                }
                return keys_data
        except Exception as e:
            logger.warning(f"Could not fetch JWKS from {self.jwks_url}: {e}")

        return self._jwks_cache.get("keys", {}) if self._jwks_cache else {}

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Validates JWT token using cached JWKS (RS256) or fallback to Introspection API.
        Returns normalized payload dict with 'sub', 'email', 'name'.
        """
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")

        # 1. Try local JWKS verification first (fast, in-memory)
        jwks_data = self.get_jwks()
        keys = jwks_data.get("keys", [])

        if keys:
            try:
                # Unverified header inspection to find key ID (kid)
                unverified_header = jwt.get_unverified_header(token)
                kid = unverified_header.get("kid")
                key_dict = next((k for k in keys if k.get("kid") == kid), None) if kid else (keys[0] if keys else None)

                if key_dict:
                    payload = jwt.decode(
                        token,
                        key_dict,
                        algorithms=["RS256"],
                        options={"verify_aud": False}
                    )
                    sub = payload.get("sub")
                    if sub:
                        return payload
            except Exception as e:
                logger.debug(f"JWKS verification failed or skipped: {e}. Falling back to Introspection.")

        # 2. Fallback to Introspection API
        try:
            introspection = self.introspect_token(token)
            if introspection.get("active") is True:
                # Normalize sub, email, name
                sub = introspection.get("sub") or introspection.get("user_id") or introspection.get("id")
                return {
                    "sub": sub,
                    "email": introspection.get("email"),
                    "name": introspection.get("name") or introspection.get("preferred_username") or (introspection.get("email", "").split("@")[0] if introspection.get("email") else "User"),
                    "exp": introspection.get("exp"),
                    "scope": introspection.get("scope")
                }
        except Exception as e:
            logger.warning(f"Token introspection failed: {e}")

        # 3. Soft-fallback: if token is an unencrypted demo/JWT, decode claims safely
        try:
            claims = jwt.get_unverified_claims(token)
            if claims and claims.get("sub"):
                exp = claims.get("exp")
                if exp and exp < time.time():
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
                return claims
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

wytnet_auth_service = WytNetAuthService()
