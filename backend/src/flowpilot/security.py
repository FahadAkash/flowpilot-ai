"""Authentication, bcrypt password hashing, and JWT helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from flowpilot.config import get_settings

MAX_BCRYPT_PASSWORD_BYTES = 72
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a new password with bcrypt, enforcing the 72 UTF-8 byte boundary."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password exceeds the 72-byte maximum length for bcrypt.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against an existing bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def hash_api_key(api_key: str) -> str:
    """Return SHA-256 hex digest of an API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def create_access_token(
    subject: str, role: str = "analyst", expires_minutes: int | None = None
) -> str:
    """Create a signed JWT bearer token."""
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT token."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
