"""Password helpers for the managed overlay."""

from __future__ import annotations

import hashlib
import hmac
import secrets


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16


def legacy_sha256_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return "scrypt$%s$%s" % (salt.hex(), derived.hex())


def _verify_scrypt(password: str, password_hash: str) -> bool:
    _, salt_hex, derived_hex = password_hash.split("$", 2)
    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    ).hex()
    return hmac.compare_digest(candidate, derived_hex)


def verify_password(password: str, password_hash: str) -> bool:
    if not isinstance(password_hash, str) or not password_hash.strip():
        return False
    normalized = password_hash.strip()
    if normalized.startswith("scrypt$"):
        try:
            return _verify_scrypt(password, normalized)
        except (ValueError, TypeError):
            return False
    candidate = legacy_sha256_password(password)
    return hmac.compare_digest(candidate, normalized)
