"""Knowledge base (FAQ) list, search, add, edit, delete."""
from __future__ import annotations


from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.demo_session import demo_blocks_mutation, demo_created
from app.models import KnowledgeItem
from app.security import require_admin, verify_csrf
from app.web import LIKE_ESCAPE, business_context, clean_query, like_term, render

# Every route in this module requires role=admin (router-level dependency);
# mutating handlers also declare it explicitly and verify CSRF.
router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/admin/knowledge", response_class=HTMLResponse)
async def knowledge_list(request: Request, db: Session = Depends(get_db), q: str = ""):
    query = db.query(KnowledgeItem)
    if q.strip():
        term = like_term(q)
        query = query.filter(KnowledgeItem.question.ilike(term, escape=LIKE_ESCAPE) | KnowledgeItem.answer.ilike(term, escape=LIKE_ESCAPE))
    items = query.order_by(KnowledgeItem.id.desc()).all()
    return render(request, "knowledge.html", business_context(db) | {"active_page": "knowledge", "items": items, "q": clean_query(q)})


@router.get("/admin/knowledge/{item_id}/edit", response_class=HTMLResponse)
async def knowledge_edit(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return render(request, "knowledge_edit.html", business_context(db) | {"active_page": "knowledge", "item": item})


@router.post("/admin/knowledge/{item_id}/edit")
async def knowledge_update(item_id: int, request: Request, question: str = Form(...), answer: str = Form(...), category: str = Form("general"), is_active: bool = Form(False), csrf_token: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    verify_csrf(request, csrf_token)
    if demo_blocks_mutation(request, "knowledge", item_id):
        raise HTTPException(status_code=403, detail="You can only edit answers you added in this demo session")
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    item.question, item.answer = question.strip()[:500], answer.strip()
    item.category, item.is_active = category.strip()[:100] or "general", is_active
    db.commit()
    return RedirectResponse("/admin/knowledge?updated=1", status_code=303)


@router.post("/admin/knowledge")
async def knowledge_add(request: Request, question: str = Form(...), answer: str = Form(...), category: str = Form("general"), csrf_token: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    verify_csrf(request, csrf_token)
    if not question.strip() or not answer.strip():
        return RedirectResponse("/admin/knowledge?error=empty", status_code=303)
    item = KnowledgeItem(question=question.strip()[:500], answer=answer.strip(), category=category.strip()[:100] or "general")
    db.add(item)
    db.commit()
    db.refresh(item)
    demo_created(request, "knowledge", item.id, item.question)
    return RedirectResponse("/admin/knowledge?added=1", status_code=303)


@router.post("/admin/knowledge/{item_id}/delete")
async def knowledge_delete(item_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    verify_csrf(request, csrf_token)
    if demo_blocks_mutation(request, "knowledge", item_id):
        raise HTTPException(status_code=403, detail="You can only delete answers you added in this demo session")
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    db.delete(item)
    db.commit()
    return RedirectResponse("/admin/knowledge?deleted=1", status_code=303)
