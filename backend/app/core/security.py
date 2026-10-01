from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    data: dict, secret_key: str, expires_minutes: int = 30
) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode["type"] = "access"
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict, secret_key: str, expires_days: int = 7
) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(days=expires_days)
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def decode_token(token: str, secret_key: str) -> dict | None:
    try:
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except Exception:
        return None
