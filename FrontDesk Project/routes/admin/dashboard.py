"""Admin dashboard metrics."""
from __future__ import annotations

from datetime import datetime, date, time, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Appointment, Conversation, KnowledgeItem, Message
from app.security import require_admin
from app.web import business_context, render

# Every route in this module requires role=admin (router-level dependency);
# mutating handlers also declare it explicitly and verify CSRF.
router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    today = datetime.combine(date.today(), time.min)
    tomorrow = today + timedelta(days=1)
    month_start = today.replace(day=1)
    conv_count = db.query(func.count(Conversation.id)).scalar() or 0
    msg_count = db.query(func.count(Message.id)).scalar() or 0
    appt_count = db.query(func.count(Appointment.id)).scalar() or 0
    upcoming_count = db.query(func.count(Appointment.id)).filter(Appointment.appointment_time >= today, Appointment.status == "confirmed").scalar() or 0
    today_count = db.query(func.count(Appointment.id)).filter(Appointment.appointment_time >= today, Appointment.appointment_time < tomorrow, Appointment.status != "cancelled").scalar() or 0
    completed_count = db.query(func.count(Appointment.id)).filter(Appointment.status == "completed").scalar() or 0
    attended_conv = db.query(func.count(func.distinct(Appointment.conversation_id))).filter(Appointment.status != "cancelled").scalar() or 0
    conversion = round(attended_conv * 100 / conv_count) if conv_count else 0
    this_month = db.query(func.count(Appointment.id)).filter(Appointment.appointment_time >= month_start).scalar() or 0
    kb_count = db.query(func.count(KnowledgeItem.id)).scalar() or 0
    recent = db.query(Conversation).options(selectinload(Conversation.messages)).order_by(Conversation.updated_at.desc()).limit(5).all()
    upcoming = db.query(Appointment).filter(Appointment.appointment_time >= today, Appointment.status == "confirmed").order_by(Appointment.appointment_time.asc()).limit(5).all()
    # Real daily conversation counts for the last seven days, normalized in Python.
    activity_start = today - timedelta(days=6)
    counts = dict(db.query(func.date(Conversation.created_at), func.count(Conversation.id)).filter(Conversation.created_at >= activity_start).group_by(func.date(Conversation.created_at)).all())
    activity = [{"label": (activity_start + timedelta(days=i)).strftime("%a"), "count": counts.get((activity_start + timedelta(days=i)).date().isoformat(), 0)} for i in range(7)]
    max_activity = max([1] + [entry["count"] for entry in activity])
    return render(request, "admin.html", business_context(db) | {
        "active_page": "dashboard", "conv_count": conv_count, "msg_count": msg_count,
        "appt_count": appt_count, "upcoming_count": upcoming_count, "today_count": today_count,
        "completed_count": completed_count, "this_month": this_month, "kb_count": kb_count,
        "conversion": conversion, "recent": recent, "upcoming": upcoming,
        "activity": activity, "max_activity": max_activity,
    })
