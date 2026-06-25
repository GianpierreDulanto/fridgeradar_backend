from fastapi import APIRouter, Depends

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
def register(body: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.register(email=body.email, password=body.password, full_name=body.full_name)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.login(email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, auth: AuthService = Depends(get_auth_service)):
    return auth.refresh(refresh_token=body.refresh_token)


@router.post("/logout")
def logout():
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user
