from abc import ABC, abstractmethod
from typing import Optional


class AuthProvider(ABC):
    """Abstract auth provider interface.

    Implementations:
      - LocalAuthProvider: JWT + bcrypt (Phase 2)
      - OIDCAuthProvider: Authentik/any OIDC (Phase 7)
    """

    @abstractmethod
    async def authenticate(self, email: str, password: str) -> Optional[dict]:
        """Validate credentials, return user dict or None."""
        ...

    @abstractmethod
    async def create_user(self, email: str, password: str, display_name: str) -> dict:
        """Register new user, return user dict."""
        ...

    @abstractmethod
    async def validate_token(self, token: str) -> Optional[dict]:
        """Validate JWT/OIDC token, return user claims or None."""
        ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> Optional[dict]:
        """Issue new access token from refresh token."""
        ...

    @abstractmethod
    async def revoke_token(self, token: str) -> None:
        """Blacklist a token (logout)."""
        ...
