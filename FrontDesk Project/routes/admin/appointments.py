"""Appointment list, search and status updates."""
from __future__ import annotations

from datetime import datetime, date, time, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Appointment
from app.security import require_admin, verify_csrf
from app.web import LIKE_ESCAPE, business_context, clean_query, like_term, page_params, pagination, render

# Every route in this module requires role=admin (router-level dependency);
# mutating handlers also declare it explicitly and verify CSRF.
router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])

APPOINTMENT_STATUSES = {"confirmed", "cancelled", "completed"}


@router.get("/admin/appointments", response_class=HTMLResponse)
async def appointments_list(request: Request, db: Session = Depends(get_db), status: str = "", q: str = ""):
    page, offset = page_params(request)
    query = db.query(Appointment)
    if status in APPOINTMENT_STATUSES:
        query = query.filter(Appointment.status == status)
    if q.strip():
        term = like_term(q)
        query = query.filter(Appointment.customer_name.ilike(term, escape=LIKE_ESCAPE) | Appointment.customer_phone.ilike(term, escape=LIKE_ESCAPE) | Appointment.service.ilike(term, escape=LIKE_ESCAPE))
    total = query.count()
    items = query.order_by(Appointment.appointment_time.asc()).offset(offset).limit(settings.page_size).all()
    today = datetime.combine(date.today(), time.min)
    confirmed_count = db.query(func.count(Appointment.id)).filter(Appointment.status == "confirmed").scalar() or 0
    today_count = db.query(func.count(Appointment.id)).filter(Appointment.appointment_time >= today, Appointment.appointment_time < today + timedelta(days=1), Appointment.status != "cancelled").scalar() or 0
    return render(request, "appointments.html", business_context(db) | {"active_page": "appointments", "items": items, "status": status, "q": clean_query(q), "confirmed_count": confirmed_count, "today_count": today_count, **pagination(request, total)})


@router.post("/admin/appointments/{appt_id}/status")
async def update_appointment_status(appt_id: int, request: Request, status: str = Form(...), csrf_token: str = Form(""), db: Session = Depends(get_db), _: None = Depends(require_admin)):
    verify_csrf(request, csrf_token)
    appt = db.get(Appointment, appt_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if status not in APPOINTMENT_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported appointment status")
    appt.status = status
    db.commit()
    return RedirectResponse("/admin/appointments?updated=1", status_code=303)
