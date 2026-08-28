"""Password and session primitives using only Python's standard library."""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    encoded = password.encode("utf-8")
    if len(encoded) > 1024:
        raise ValueError("Пароль слишком длинный")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(encoded, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return salt, digest


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    try:
        _, actual = hash_password(password, salt)
    except (ValueError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()
