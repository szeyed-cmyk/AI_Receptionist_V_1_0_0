"""Chat orchestration: create/bind conversation, persist messages, call AI."""
from __future__ import annotations

import secrets
import re
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.ai_service import generate_reply
from app.ai_service import get_setting
from app.models import Conversation, Message


SESSION_CONV_KEY = "visitor_conversation_id"
SESSION_TOKEN_KEY = "visitor_token"


def _visitor_token(request: Request) -> str:
    token = request.session.get(SESSION_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        request.session[SESSION_TOKEN_KEY] = token
    return token


async def handle_chat_async(db: Session, request: Request, message: str) -> dict:
    token = _visitor_token(request)
    session_conv_id = request.session.get(SESSION_CONV_KEY)

    conv: Conversation | None = None
    if session_conv_id is not None:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == session_conv_id,
                Conversation.visitor_token == token,
            )
            .first()
        )

    if conv is None:
        conv = Conversation(channel="web", visitor_token=token)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        request.session[SESSION_CONV_KEY] = conv.id
        if settings.demo_mode and request.session.get("demo_session"):
            from app.demo_session import demo_created
            demo_created(request, "conversation", conv.id, (message or "Web conversation")[:100])

    user_msg = Message(conversation_id=conv.id, role="user", content=message)
    db.add(user_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Demo sessions cannot reach production integrations or paid AI services.
    from app.demo_ai import local_demo_reply
    from app.models import KnowledgeItem

    if settings.demo_mode:
        fields = re.search(r"(.+?),\s*([+0-9][0-9 ()-]{5,}),\s*(.+?),\s*(.+)", message, re.IGNORECASE)
        booking_request = bool(fields) or any(word in message.lower() for word in ("book", "appointment", "reserve"))
        reply = "" if booking_request else local_demo_reply(
            message, db.query(KnowledgeItem).filter(KnowledgeItem.is_active == True).all()
        )
        if booking_request:
            # Booking intent takes precedence over broad FAQ keyword matches.
            if fields:
                name, phone, service, when = [part.strip() for part in fields.groups()]
                # "I would like to book an appointment name: Ahmad" -> "Ahmad"
                labelled = re.search(r"\bname\s*[:=\-]\s*(.+)$", name, re.IGNORECASE)
                if labelled:
                    name = labelled.group(1).strip()
                if len(name) < 2 or len(name) > 100 or len(service) > 150 or len(when) > 150:
                    reply = "Please provide a valid name, service and preferred time so I can check the appointment."
                else:
                    from app.ai_service import book_appointment_tool
                    result = book_appointment_tool(db, conv.id, name, phone, service, when)
                    reply = result.get("message") or result.get("error")
            else:
                from app.demo_ai import BOOKING_PROMPT
                reply = BOOKING_PROMPT
    else:
        reply = await generate_reply(db, conv.id, message)
    assistant_msg = Message(conversation_id=conv.id, role="assistant", content=reply)
    db.add(assistant_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"conversation_id": conv.id, "reply": reply}


def reject_foreign_conversation(db: Session, request: Request, conversation_id: int | None) -> None:
    """If the client sends a conversation_id that is not theirs, raise 403.

    Used by the public route to make ownership checks explicit for auditors.
    The service itself never trusts the client id for loading history.
    """
    if conversation_id is None:
        return
    token = request.session.get(SESSION_TOKEN_KEY)
    session_conv_id = request.session.get(SESSION_CONV_KEY)
    if session_conv_id is not None and int(conversation_id) == int(session_conv_id):
        # Matches the session-owned conversation — OK (still re-verified by token).
        if token:
            owned = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.visitor_token == token,
                )
                .first()
            )
            if owned:
                return
        raise HTTPException(status_code=403, detail="Conversation does not belong to this visitor")
    # Client tried a foreign / guessed sequential id
    raise HTTPException(status_code=403, detail="Conversation does not belong to this visitor")
