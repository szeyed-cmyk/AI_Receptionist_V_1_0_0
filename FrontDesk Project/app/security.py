"""Authorization guards, CSRF, rate limiting, and shared web helpers.

Role model
----------
FrontDesk AI has a single administrative role: ``admin``.

On successful login or first-time setup the session stores::

    request.session["user"] = "<username>"
    request.session["role"] = "admin"

``require_admin`` is the only route guard. It must be attached to every
admin page and every mutating admin endpoint so auditors can trace
authorization from the route signature to this module.
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from app.config import settings

ADMIN_ROLE = "admin"

# In-memory rate-limit buckets. Keyed by (bucket_name, client_ip).
_ATTEMPTS: dict[tuple[str, str], list[float]] = defaultdict(list)


def is_demo(request: Request) -> bool:
    """True only for sessions created by the CSRF-protected demo endpoint."""
    return settings.demo_mode and request.session.get("demo_session") is True


def require_demo_config() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")


def block_demo_sensitive_action(request: Request) -> None:
    """No demo reviews/bypasses: privileged writes are unavailable by design."""
    if settings.demo_mode:
        # Demonstration instances contain synthetic data only, and account/API
        # credentials must never be writable from a shared public environment.
        raise HTTPException(status_code=403, detail="Privileged settings edits are disabled in demo mode")


def current_role(request: Request) -> str | None:
    """Return the role stored in the signed session, if any."""
    # Signed demo cookies never carry access when the process leaves demo mode;
    # production cookies never carry access after it is switched to demo mode.
    if (request.session.get("demo_session") is True) is not settings.demo_mode:
        return None
    role = request.session.get("role")
    if role:
        return str(role)
    # Legacy session key from earlier builds — treat as admin if present
    if request.session.get("admin") is True:
        return ADMIN_ROLE
    return None


def current_user(request: Request) -> str | None:
    return request.session.get("user") or request.session.get("admin_user")


def require_admin(request: Request) -> None:
    """FastAPI dependency: reject the request unless the session role is admin.

    Used as::

        APIRouter(dependencies=[Depends(require_admin)])
        # and also on each mutating handler:
        async def save(..., _: None = Depends(require_admin)):
    """
    if current_role(request) != ADMIN_ROLE:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


def set_admin_session(request: Request, username: str) -> None:
    """Mark the signed session as an authenticated admin."""
    request.session.clear()
    request.session["user"] = username
    request.session["role"] = ADMIN_ROLE
    # Kept for template compatibility with older HTML that checked session.admin
    request.session["admin"] = True
    request.session["admin_user"] = username


def client_ip(request: Request) -> str:
    """Return the direct peer IP.

    Uses ``request.client.host`` only. Do **not** trust ``X-Forwarded-For``
    unless uvicorn is started with ``--proxy-headers`` and
    ``--forwarded-allow-ips`` restricted to your reverse proxy. See
    HowToSetup.md and docs/SECURITY.md.
    """
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit(bucket: str, ip: str, max_attempts: int, window_sec: int) -> bool:
    """Return True if the attempt is allowed; False if the caller is throttled."""
    now = time.time()
    key = (bucket, ip)
    recent = [t for t in _ATTEMPTS[key] if now - t < window_sec]
    _ATTEMPTS[key] = recent
    if len(recent) >= max_attempts:
        return False
    _ATTEMPTS[key].append(now)
    return True


def rate_limit_login(ip: str) -> bool:
    return rate_limit(
        "login",
        ip,
        settings.login_max_attempts,
        settings.login_window_sec,
    )


def rate_limit_setup(ip: str) -> bool:
    """Throttle /admin/setup POSTs per client IP (default 5 per 15 minutes)."""
    return rate_limit(
        "setup",
        ip,
        settings.setup_max_attempts,
        settings.setup_window_sec,
    )


def rate_limit_chat(ip: str) -> bool:
    return rate_limit(
        "chat",
        ip,
        settings.chat_max_attempts,
        settings.chat_window_sec,
    )


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


class CsrfError(HTTPException):
    """403 for a missing/mismatched CSRF token (handled in app/__init__.py)."""

    def __init__(self) -> None:
        super().__init__(status_code=403, detail="Invalid CSRF token")


def verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf_token") or ""
    provided = token or ""
    if not expected or not secrets.compare_digest(expected, provided):
        raise CsrfError()


def rotate_csrf(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return token


def ensure_password_hash(db) -> str:
    """Load the stored admin password hash; bootstrap from ADMIN_PASSWORD env if needed.

    Plaintext values are never accepted for login. If a legacy plaintext value
    is found in the database it is rejected (returns empty) so the operator
    must reset via SETUP_TOKEN / ADMIN_PASSWORD bootstrap.
    """
    from app.ai_service import get_setting, set_setting
    from app.auth import hash_password, is_hashed
    from app.config import settings as cfg

    stored = get_setting(db, "admin_password", "") or ""
    if stored and not is_hashed(stored):
        # Refuse to promote plaintext; wipe so setup/bootstrap can recreate.
        set_setting(db, "admin_password", "")
        return ""
    if not stored and cfg.admin_password:
        set_setting(db, "admin_username", cfg.admin_username or "admin")
        set_setting(db, "admin_password", hash_password(cfg.admin_password))
        set_setting(db, "admin_role", "admin")
        return get_setting(db, "admin_password", "") or ""
    return stored


def admin_username(db) -> str:
    from app.ai_service import get_setting
    from app.config import settings as cfg

    return get_setting(db, "admin_username", cfg.admin_username or "admin") or "admin"


def setup_is_available(db) -> bool:
    """True only when no admin exists yet AND ADMIN_PASSWORD bootstrap is unused."""
    from app.ai_service import get_setting
    from app.config import settings as cfg

    if get_setting(db, "admin_password", ""):
        return False
    if (cfg.admin_password or "").strip():
        return False
    return True


def require_setup_token(provided: str) -> None:
    """Raise 403 unless the submitted token matches SETUP_TOKEN from the environment."""
    from app.config import settings as cfg

    expected = (cfg.setup_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="SETUP_TOKEN is not configured. Set SETUP_TOKEN in .env before using /admin/setup.",
        )
    if not secrets.compare_digest(expected, (provided or "").strip()):
        raise HTTPException(status_code=403, detail="Invalid setup token")
