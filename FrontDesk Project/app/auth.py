"""Admin password helpers. Passwords are stored as bcrypt hashes only."""
from __future__ import annotations

import secrets

import bcrypt

WEAK_PASSWORDS = {
    "admin123",
    "admin",
    "password",
    "CHANGE_ME",
    "change-me",
    "change-this-to-a-long-random-string-in-production",
}


def is_hashed(value: str) -> bool:
    return bool(value) and value.startswith("$2")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, stored: str) -> bool:
    """Verify a password against a bcrypt hash. Plaintext stored values are rejected."""
    if not stored or plain is None:
        return False
    if not is_hashed(stored):
        # Legacy plaintext is no longer accepted.
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def usernames_match(provided: str, expected: str) -> bool:
    """Constant-time username compare (same length padding)."""
    a = (provided or "").strip()
    b = (expected or "").strip()
    max_len = max(len(a), len(b), 1)
    return secrets.compare_digest(a.ljust(max_len), b.ljust(max_len)) and len(a) == len(b)


def is_weak_password(password: str) -> bool:
    return (password or "").strip() in WEAK_PASSWORDS
