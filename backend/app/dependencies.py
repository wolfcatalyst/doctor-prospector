from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.auth.token_store import get_token_store
from app.core.security import decode_token
from app.db.engine import get_db

# Optional bearer - won't raise 403 if missing
optional_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current user from JWT token.

    When AUTH_ENABLED=false (dev mode), returns a fake dev user.
    When AUTH_ENABLED=true, validates the JWT and returns user claims.
    """
    if not settings.auth_enabled:
        return {
            "id": "00000000-0000-0000-0000-000000000000",
            "email": "dev@doctorprospector.local",
            "display_name": "Dev User",
            "role": "admin",
        }

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(credentials.credentials, settings.secret_key)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if await get_token_store().is_revoked(credentials.credentials):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "display_name": payload.get("display_name", ""),
        "role": payload.get("role", "user"),
    }


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_active_device_profile(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resolve the user's active device market profile filters.

    Falls back to the TAVR preset when no profile is active or auth is disabled.
    """
    from app.services.device_profile_service import get_active_profile
    return await get_active_profile(user["id"], db)
