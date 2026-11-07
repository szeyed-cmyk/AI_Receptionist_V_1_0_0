"""Booking rule tests (hours, holiday, overlap, duplicate phone). AI is not called."""
from __future__ import annotations

from datetime import datetime, timedelta


def _next_weekday(target: int, hour: int = 10) -> datetime:
    """Return the next datetime falling on weekday target (0=Mon .. 6=Sun) at hour."""
    now = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    days_ahead = (target - now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


def _booking_api():
    """Import after the client fixture has rebound the DB engine."""
    from app.database import SessionLocal
    from app.ai_service import book_appointment_tool, set_setting
    from app.models import Conversation

    return SessionLocal, book_appointment_tool, set_setting, Conversation


def test_booking_rejects_sunday(client):
    SessionLocal, book_appointment_tool, _, Conversation = _booking_api()
    db = SessionLocal()
    conv = Conversation(channel="web")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    sunday = _next_weekday(6, 10)
    result = book_appointment_tool(
        db,
        conv.id,
        "Pat",
        "5551110001",
        "Checkup",
        sunday.strftime("%A %I:%M %p"),
    )
    assert result["success"] is False
    assert "closed" in result["error"].lower()
    db.close()


def test_booking_rejects_outside_hours(client):
    SessionLocal, book_appointment_tool, _, Conversation = _booking_api()
    db = SessionLocal()
    conv = Conversation(channel="web")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    monday = _next_weekday(0, 8)  # 8 AM — before opening
    result = book_appointment_tool(
        db,
        conv.id,
        "Pat",
        "5551110002",
        "Checkup",
        monday.strftime("%A %I:%M %p"),
    )
    assert result["success"] is False
    assert "between" in result["error"].lower() or "9" in result["error"]
    db.close()


def test_booking_rejects_holiday(client):
    SessionLocal, book_appointment_tool, set_setting, Conversation = _booking_api()
    db = SessionLocal()
    conv = Conversation(channel="web")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    tomorrow = datetime.now() + timedelta(days=1)
    while tomorrow.weekday() == 6:
        tomorrow += timedelta(days=1)
    holiday = tomorrow.strftime("%Y-%m-%d")
    set_setting(db, "holiday_dates", holiday)

    when = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    result = book_appointment_tool(
        db,
        conv.id,
        "Pat",
        "5551110003",
        "Checkup",
        when.strftime("%Y-%m-%d %H:%M"),
    )
    assert result["success"] is False
    assert "holiday" in result["error"].lower()
    db.close()


def test_booking_rejects_overlap_and_duplicate_phone(client):
    SessionLocal, book_appointment_tool, _, Conversation = _booking_api()
    db = SessionLocal()
    conv = Conversation(channel="web")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    slot = _next_weekday(0, 10)
    when_text = slot.strftime("%A at %I:%M %p")

    ok = book_appointment_tool(
        db,
        conv.id,
        "Pat",
        "5559998888",
        "Checkup",
        when_text,
    )
    assert ok["success"] is True, ok

    overlap = book_appointment_tool(
        db,
        conv.id,
        "Other",
        "5559997777",
        "Checkup",
        when_text,
    )
    assert overlap["success"] is False
    assert "overlap" in overlap["error"].lower()

    later = slot.replace(hour=14)
    dup = book_appointment_tool(
        db,
        conv.id,
        "Pat",
        "5559998888",
        "Follow-up",
        later.strftime("%A at %I:%M %p"),
    )
    assert dup["success"] is False
    assert "phone" in dup["error"].lower()
    db.close()


def test_booking_accepts_saturday(client):
    """Saturday is open by default (seed/docs)."""
    SessionLocal, book_appointment_tool, _, Conversation = _booking_api()
    db = SessionLocal()
    conv = Conversation(channel="web")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    saturday = _next_weekday(5, 11)
    result = book_appointment_tool(
        db,
        conv.id,
        "Sam",
        "5552223333",
        "Consult",
        saturday.strftime("%A at %I:%M %p"),
    )
    assert result["success"] is True, result
    db.close()
