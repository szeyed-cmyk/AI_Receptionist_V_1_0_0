"""Public (unauthenticated) routes.

These endpoints are intentionally public: a receptionist product must let
visitors chat and book without an admin login. They create conversation /
message / appointment rows on behalf of the visitor. See docs/SECURITY.md
for the public allowlist and the rationale.

POST /chat controls:
- Conversation ownership is bound to the signed visitor session (random
  visitor_token). Client-supplied sequential conversation_id values that do
  not match the session are rejected with 403.
- Per-IP rate limit keyed on request.client.host (not X-Forwarded-For).
- Message length capped at settings.chat_message_max_length (default 2000).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.chat_service import handle_chat_async, reject_foreign_conversation
from app.config import settings
from app.database import get_db
from app.security import client_ip, rate_limit_chat
from app.templating import templates

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Product landing page. The visitor chat is available at /chat."""
    return templates.TemplateResponse(
        request, "landing.html", {"request": request, "demo_mode": settings.demo_mode}
    )


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Public customer chat page."""
    return templates.TemplateResponse(
        request, "chat.html", {"request": request, "demo_mode": settings.demo_mode}
    )


@router.post("/chat")
async def web_chat(
    request: Request,
    message: str = Form(..., max_length=settings.chat_message_max_length),
    conversation_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Public chat + booking entry point (creates conversation/message rows).

    get_db creates a local public-demo scope as a fallback before loading
    data. Both public chat and private admin operations can therefore run
    without an existing preselected engine or any production credentials.
    Ownership: session-bound visitor_token; foreign conversation_id → 403.
    """
    if settings.demo_mode and not request.session.get("demo_scope"):
        import secrets
        request.session["demo_scope"] = secrets.token_urlsafe(24)

    if len(message) > settings.chat_message_max_length:
        raise HTTPException(status_code=413, detail="Message too long")

    ip = client_ip(request)
    if not rate_limit_chat(ip):
        raise HTTPException(status_code=429, detail="Too many chat requests. Please wait and try again.")

    # Explicit ownership check for auditors: reject guessed sequential IDs.
    reject_foreign_conversation(db, request, conversation_id)

    return await handle_chat_async(db, request, message)
