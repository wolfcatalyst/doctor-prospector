import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.engine import get_db
from app.auth.token_store import get_token_store
from app.core.security import decode_token
from app.dependencies import get_current_user, optional_bearer
from app.auth.local_provider import LocalAuthProvider
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


def _get_auth_provider(settings: Settings) -> LocalAuthProvider:
    return LocalAuthProvider(
        secret_key=settings.secret_key,
        access_expire_minutes=settings.access_token_expire_minutes,
        refresh_expire_days=settings.refresh_token_expire_days,
    )


@router.post("/register", response_model=UserResponse)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Register a new user account."""
    provider = _get_auth_provider(settings)
    try:
        user = await provider.create_user(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            db=db,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Authenticate and receive JWT tokens."""
    provider = _get_auth_provider(settings)
    user = await provider.authenticate(email=body.email, password=body.password, db=db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tokens = provider.create_tokens_for_user(user)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Refresh access token using refresh token."""
    provider = _get_auth_provider(settings)
    tokens = await provider.refresh_token(body.refresh_token, db=db)
    if not tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return tokens


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user profile."""
    return user


@router.post("/logout")
async def logout(
    user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    settings: Settings = Depends(get_settings),
):
    """Logout: revoke the access token until it would have expired.

    Stored in Redis when REDIS_URL is set, otherwise in memory.
    """
    if credentials:
        payload = decode_token(credentials.credentials, settings.secret_key) or {}
        ttl = int(payload.get("exp", time.time()) - time.time())
        await get_token_store().revoke(credentials.credentials, ttl)
    return {"message": "Logged out successfully"}
