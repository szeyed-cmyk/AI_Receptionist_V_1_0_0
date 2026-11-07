"""Login / setup / logout — intentionally unguarded.

- ``/admin/setup`` requires SETUP_TOKEN and is disabled when an admin already
  exists or when ADMIN_PASSWORD env bootstrap is configured.
- ``/admin/login`` authenticates and writes role=admin into the signed session.
- ``/admin/logout`` clears the session.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.ai_service import get_setting, set_setting
from app.auth import hash_password, is_weak_password, usernames_match, verify_password
from app.config import settings
from app.database import get_db
from app.security import (
    admin_username,
    block_demo_sensitive_action,
    client_ip,
    ensure_password_hash,
    rate_limit_login,
    rate_limit_setup,
    require_demo_config,
    require_setup_token,
    rotate_csrf,
    set_admin_session,
    setup_is_available,
    verify_csrf,
)
from app.web import render

router = APIRouter(tags=["auth"])


@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    if settings.demo_mode:
        # An anonymous request uses the bootstrap DB only as the rendered login
        # page is prepared. No production credential lookup ever happens.
        return render(request, "login.html", {"demo_mode": True})
    if setup_is_available(db):
        return RedirectResponse("/admin/setup", status_code=303)
    ensure_password_hash(db)
    return render(request, "login.html", {"demo_mode": False})


@router.post("/admin/login")
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if settings.demo_mode:
        raise HTTPException(status_code=403, detail="Use the Admin demo button in demo mode")
    verify_csrf(request, csrf_token)
    if not rate_limit_login(client_ip(request)):
        return RedirectResponse("/admin/login?error=rate", status_code=303)

    stored = ensure_password_hash(db)
    if not stored:
        if setup_is_available(db):
            return RedirectResponse("/admin/setup", status_code=303)
        return RedirectResponse("/admin/login?error=1", status_code=303)

    user_ok = usernames_match(username, admin_username(db))
    pass_ok = verify_password(password, stored)
    if user_ok and pass_ok:
        if not get_setting(db, "admin_role", ""):
            set_setting(db, "admin_role", "admin")
        set_admin_session(request, admin_username(db))
        rotate_csrf(request)
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin/login?error=1", status_code=303)


@router.get("/admin/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: Session = Depends(get_db)):
    if settings.demo_mode:
        return RedirectResponse("/admin/login", status_code=303)
    if not setup_is_available(db):
        return RedirectResponse("/admin/login", status_code=303)
    if not (settings.setup_token or "").strip():
        return render(
            request,
            "setup.html",
            {"setup_blocked": True, "error": "missing_token_config"},
        )
    return render(request, "setup.html", {"setup_blocked": False})


@router.post("/admin/setup")
async def do_setup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    setup_token: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create the first admin. Requires SETUP_TOKEN; refused if admin exists."""
    block_demo_sensitive_action(request)
    verify_csrf(request, csrf_token)
    if not setup_is_available(db):
        return RedirectResponse("/admin/login", status_code=303)
    # Per-client throttle BEFORE the token compare so SETUP_TOKEN cannot be
    # brute-forced; require_setup_token uses secrets.compare_digest.
    if not rate_limit_setup(client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many setup attempts. Please wait and try again.")
    require_setup_token(setup_token)
    if password != confirm_password:
        return RedirectResponse("/admin/setup?error=mismatch", status_code=303)
    if len(password) < 8 or is_weak_password(password):
        return RedirectResponse("/admin/setup?error=too_short", status_code=303)
    uname = username.strip() or "admin"
    set_setting(db, "admin_username", uname)
    set_setting(db, "admin_password", hash_password(password))
    set_setting(db, "admin_role", "admin")
    set_admin_session(request, uname)
    rotate_csrf(request)
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/demo-login")
async def demo_login(
    request: Request,
    csrf_token: str = Form(""),
):
    """Create a signed admin session with a fresh fictional-data sandbox."""
    from app.database import registry

    require_demo_config()
    verify_csrf(request, csrf_token)
    if not rate_limit_login("demo:" + client_ip(request)):
        return RedirectResponse("/admin/login?error=rate", status_code=303)
    scope = secrets.token_urlsafe(24)
    if not registry.can_create_demo(scope):
        return RedirectResponse("/admin/login?error=busy", status_code=303)
    registry.bind(scope)
    set_admin_session(request, "Demo Administrator")
    request.session["demo_session"] = True
    request.session["demo_scope"] = scope
    rotate_csrf(request)
    # The following request gets this scope from the middleware and sees only
    # this reviewer's seeded appointments, FAQs, conversations and chat rows.
    return RedirectResponse("/admin", status_code=303)


@router.get("/admin/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
