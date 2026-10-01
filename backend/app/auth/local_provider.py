"""Local JWT + bcrypt authentication provider."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthProvider
from app.auth.token_store import get_token_store
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User


class LocalAuthProvider(AuthProvider):
    """JWT + bcrypt authentication.

    - Passwords hashed with bcrypt
    - Access tokens: configurable expiry (default 30 min), HS256
    - Refresh tokens: configurable expiry (default 7 days)
    - Token blacklist via Redis (for logout)
    """

    def __init__(self, secret_key: str, access_expire_minutes: int = 30, refresh_expire_days: int = 7):
        self.secret_key = secret_key
        self.access_expire_minutes = access_expire_minutes
        self.refresh_expire_days = refresh_expire_days

    async def authenticate(self, email: str, password: str, db: AsyncSession = None) -> Optional[dict]:
        if not db:
            return None
        result = await db.execute(select(User).where(User.email == email, User.is_active == True))
        user = result.scalar_one_or_none()
        if not user or not user.password_hash:
            return None
        if not verify_password(password, user.password_hash):
            return None

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

        return self._user_to_dict(user)

    async def create_user(self, email: str, password: str, display_name: str, db: AsyncSession = None) -> dict:
        if not db:
            raise ValueError("Database session required")

        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")

        user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role="user",
            auth_provider="local",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return self._user_to_dict(user)

    async def validate_token(self, token: str) -> Optional[dict]:
        if await get_token_store().is_revoked(token):
            return None

        payload = decode_token(token, self.secret_key)
        if not payload:
            return None
        if payload.get("type") != "access":
            return None
        return payload

    async def refresh_token(self, refresh_token_str: str, db: AsyncSession = None) -> Optional[dict]:
        payload = decode_token(refresh_token_str, self.secret_key)
        if not payload or payload.get("type") != "refresh":
            return None

        # Verify user still exists and is active
        if db:
            user_id = payload.get("sub")
            result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
            user = result.scalar_one_or_none()
            if not user:
                return None

        return self._create_tokens(payload)

    async def revoke_token(self, token: str) -> None:
        # Revoke for the remaining TTL (max 7 days)
        await get_token_store().revoke(token, 7 * 24 * 3600)

    def create_tokens_for_user(self, user_dict: dict) -> dict:
        """Create access + refresh tokens for a user."""
        return self._create_tokens(user_dict)

    def _create_tokens(self, user_data: dict) -> dict:
        token_data = {
            "sub": str(user_data.get("id", user_data.get("sub", ""))),
            "email": user_data.get("email", ""),
            "display_name": user_data.get("display_name", ""),
            "role": user_data.get("role", "user"),
        }
        return {
            "access_token": create_access_token(token_data, self.secret_key, self.access_expire_minutes),
            "refresh_token": create_refresh_token(token_data, self.secret_key, self.refresh_expire_days),
            "token_type": "bearer",
            "expires_in": self.access_expire_minutes * 60,
        }

    @staticmethod
    def _user_to_dict(user: User) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
