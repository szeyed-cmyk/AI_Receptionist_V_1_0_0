"""Conversation list, detail and delete."""
from __future__ import annotations


from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.demo_session import demo_blocks_mutation
from app.models import Conversation
from app.security import require_admin, verify_csrf
from app.web import LIKE_ESCAPE, business_context, clean_query, like_term, page_params, pagination, render

# Every route in this module requires role=admin (router-level dependency);
# mutating handlers also declare it explicitly and verify CSRF.
router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/admin/conversations", response_class=HTMLResponse)
async def conversations_list(request: Request, db: Session = Depends(get_db), q: str = ""):
    page, offset = page_params(request)
    query = db.query(Conversation)
    if q.strip():
        term = like_term(q)
        query = query.filter(Conversation.customer_name.ilike(term, escape=LIKE_ESCAPE) | Conversation.customer_phone.ilike(term, escape=LIKE_ESCAPE))
    total = query.count()
    items = query.options(selectinload(Conversation.messages)).order_by(Conversation.updated_at.desc()).offset(offset).limit(settings.page_size).all()
    return render(request, "conversations.html", business_context(db) | {"active_page": "conversations", "items": items, "q": clean_query(q), **pagination(request, total)})


@router.get("/admin/conversations/{conv_id}", response_class=HTMLResponse)
async def conversation_detail(conv_id: int, request: Request, db: Session = Depends(get_db)):
    conv = db.query(Conversation).options(selectinload(Conversation.messages)).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return render(request, "conversation_detail.html", business_context(db) | {"active_page": "conversations", "conv": conv})


@router.post("/admin/conversations/{conv_id}/delete")
async def conversation_delete(conv_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    verify_csrf(request, csrf_token)
    if demo_blocks_mutation(request, "conversation", conv_id):
        raise HTTPException(status_code=403, detail="You can only delete conversations you started in this demo session")
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return RedirectResponse("/admin/conversations?deleted=1", status_code=303)
