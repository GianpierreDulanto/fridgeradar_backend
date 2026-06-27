from fastapi import APIRouter, Depends, Request

from app.core.rate_limit import AUTH_LIMIT, limiter
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService, get_auth_service, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def register(request: Request, body: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.register(email=body.email, password=body.password, full_name=body.full_name)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, body: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.login(email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def refresh(request: Request, body: RefreshRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.refresh(refresh_token=body.refresh_token)


@router.post("/logout")
@limiter.limit(AUTH_LIMIT)
def logout(request: Request):
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user
