"""Opt-in, self-contained demo data. No credentials or external integrations."""
from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.ai_service import set_setting
from app.config import settings
from app.models import Appointment, Conversation, KnowledgeItem


def ensure_demo_admin(db: Session) -> None:
    """Create only an unguessable, never-displayed demo credential hash.

    Demo sign-in is intentionally gated by DEMO_MODE and its CSRF-protected
    endpoint; this hash cannot be used to enter the production database.
    """
    from app.security import ensure_password_hash

    if settings.demo_mode and not ensure_password_hash(db):
        from app.auth import hash_password

        set_setting(db, "admin_username", "demo-admin")
        set_setting(db, "admin_password", hash_password(secrets.token_urlsafe(48)))
        set_setting(db, "admin_role", "admin")


def _next_free_slot(db: Session, day: date, hour: int) -> datetime:
    slot = datetime.combine(day, time(hour, 0))
    while any(a[0] <= slot < a[0] + timedelta(minutes=a[1] or 60) for a in db.query(Appointment.appointment_time, Appointment.duration_minutes).filter(Appointment.status == "confirmed").all()):
        slot += timedelta(hours=1)
    return slot


def seed_demo_data(db: Session) -> None:
    """Seed isolated fictional data for one signed reviewer scope."""
    if not settings.demo_mode or db.query(KnowledgeItem.id).first():
        return
    from app.ai_service import set_setting
    for key, value in {"business_name": "Lumen Dental Studio", "opening_hour": "9", "closing_hour": "18", "closed_days": "sunday", "holiday_dates": "", "ai_base_url": "", "ai_api_key": "", "ai_model": "local-demo", "admin_role": "admin"}.items():
        set_setting(db, key, value)
    faqs = [
        ("What are your opening hours?", "We are open Monday to Saturday from 9 AM to 6 PM. We are closed on Sundays.", "Practice"),
        ("How long is an appointment?", "Every appointment reserves a full 60-minute slot.", "Booking"),
        ("Which treatments can I book?", "Choose a dental checkup, cleaning, whitening consultation, or treatment consultation.", "Treatments"),
        ("Can I reschedule?", "Yes. The clinic team can cancel a booking and arrange a new time.", "Booking"),
        ("How should I prepare for a checkup?", "Arrive ten minutes early and bring any relevant treatment history.", "Patient care"),
        ("Do you offer teeth whitening?", "Yes. Book a whitening consultation to discuss suitability and treatment options.", "Treatments"),
    ]
    db.add_all([KnowledgeItem(question=q, answer=a, category=c) for q, a, c in faqs])
    today = datetime.now().date()
    samples = [
        ("Alex Rivera", "555-0101", "Dental checkup", 0, 10, "confirmed"),
        ("Jordan Lee", "555-0102", "Cleaning", 1, 11, "confirmed"),
        ("Morgan Taylor", "555-0103", "Whitening consultation", 2, 14, "confirmed"),
        ("Casey Morgan", "555-0104", "Treatment consultation", 3, 9, "confirmed"),
        ("Jamie Parker", "555-0105", "Dental checkup", -4, 15, "completed"),
        ("Riley Chen", "555-0106", "Cleaning", -3, 10, "completed"),
    ]
    from app.models import Message
    for i, (name, phone, service, day, hour, status) in enumerate(samples):
        stamp = datetime.combine(today + timedelta(days=day), time(hour, 0))
        if stamp.weekday() == 6:
            stamp += timedelta(days=1)
        if status == "confirmed":
            db.flush()
            stamp = _next_free_slot(db, stamp.date(), stamp.hour)
        conv = Conversation(channel="web", visitor_token=f"seeded-{i}", customer_name=name, customer_phone=phone, status="active" if status == "confirmed" else "closed", created_at=stamp - timedelta(hours=3), updated_at=stamp - timedelta(hours=2))
        db.add(conv)
        db.flush()
        db.add_all([
            Message(conversation_id=conv.id, role="user", created_at=stamp - timedelta(hours=3), content=f"Hi, I would like to book a {service.lower()}."),
            Message(conversation_id=conv.id, role="assistant", created_at=stamp - timedelta(hours=3), content=f"Certainly. {name.split()[0]}, your {service.lower()} is booked for {stamp.strftime('%A at %I:%M %p')}."),
            Message(conversation_id=conv.id, role="user", created_at=stamp - timedelta(hours=2), content="Thank you for your help."),
        ])
        db.add(Appointment(conversation_id=conv.id, customer_name=name, customer_phone=phone, service=service, appointment_time=stamp, duration_minutes=60, status=status, notes="Fictional demonstration booking"))
    db.commit()
