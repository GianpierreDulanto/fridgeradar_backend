from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import AUTH_LIMIT, limiter
from app.core.security import decode_token, revoke_token
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService, get_auth_service, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/register", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
):
    return auth.register(email=body.email, password=body.password, full_name=body.full_name)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
):
    return auth.login(email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
):
    return auth.refresh(refresh_token=body.refresh_token)


@router.post("/logout")
@limiter.limit(AUTH_LIMIT)
def logout(
    request: Request,
    response: Response,
    body: LogoutRequest | None = None,
    db: Session = Depends(get_db),
    token=Depends(_bearer),
):
    """RF-AUT-004: revoke the access token (and the refresh token if sent).

    The access token is taken from the Authorization header; the refresh token
    must be sent in the body. Both end up in `token_blacklist` so any
    subsequent request carrying them is rejected with 401.
    """
    from datetime import datetime, timezone

    revoked = {"access": False, "refresh": False}

    def _revoke(jwt_str: str) -> bool:
        payload = decode_token(jwt_str)
        if not (payload and payload.get("jti") and payload.get("sub") and payload.get("exp")):
            return False
        exp_ts = payload["exp"]
        expires_at = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            if isinstance(exp_ts, (int, float))
            else exp_ts
        )
        revoke_token(
            jti=payload["jti"],
            user_id=payload["sub"],
            expires_at=expires_at,
            db=db,
            reason="logout",
        )
        return True

    if token is not None:
        revoked["access"] = _revoke(token.credentials)

    if body and body.refresh_token:
        revoked["refresh"] = _revoke(body.refresh_token)

    return {"message": "Logged out", "revoked": revoked}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user
