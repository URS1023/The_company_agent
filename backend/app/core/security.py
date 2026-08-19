from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if not password or len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    # MySQL DATETIME stores no timezone; persist and compare naive UTC values.
    return datetime.now(UTC).replace(tzinfo=None)


def expires_after(seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=seconds)


__all__ = [
    "digest_token",
    "expires_after",
    "hash_password",
    "new_session_token",
    "utc_now",
    "verify_password",
]
