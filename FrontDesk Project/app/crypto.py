"""Encrypt sensitive settings values (e.g. AI API key) at rest with Fernet.

The Fernet key is derived from SECRET_KEY via SHA-256 so operators only need
to manage one secret. Values that do not start with the ``enc:`` prefix are
treated as legacy plaintext and re-encrypted on next write.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_PREFIX = "enc:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    token = _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
    return _PREFIX + token


def decrypt_secret(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        # Legacy plaintext — return as-is so callers can migrate on write.
        return stored
    try:
        return _fernet().decrypt(stored[len(_PREFIX) :].encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""
