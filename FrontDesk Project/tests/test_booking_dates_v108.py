"""v1.0.8: booking dates are parsed strictly; weekday always from the real date."""
from __future__ import annotations

import re
from datetime import datetime

import pytest

NOW = datetime(2026, 11, 7, 19, 0)  # Saturday, Asia/Dhaka wall clock


def parse(text, now=NOW):
    from app.datetime_parse import parse_booking_datetime
    return parse_booking_datetime(text, now)


@pytest.mark.parametrize("text,expected", [
    ("day after tomorrow at 5pm", datetime(2026, 11, 9, 17)),          # Monday
    ("the day after tomorrow at 5pm", datetime(2026, 11, 9, 17)),
    ("on 10th November at 5pm", datetime(2026, 11, 10, 17)),           # Tuesday
    ("10th november at 10am", datetime(2026, 11, 10, 10)),
    ("10 November 10:30", datetime(2026, 11, 10, 10, 30)),
    ("November 10 at 2pm", datetime(2026, 11, 10, 14)),
    ("Nov 10th, 2026 at 2 pm", datetime(2026, 11, 10, 14)),
    ("10th of November 2026 at 11am", datetime(2026, 11, 10, 11)),
    ("2026-11-10 17:00", datetime(2026, 11, 10, 17)),
    ("tomorrow at 10am", datetime(2026, 11, 8, 10)),                   # Sunday (closed later)
    ("Tuesday 10 November at 5pm", datetime(2026, 11, 10, 17)),
    ("next Monday at 3pm", datetime(2026, 11, 9, 15)),
    ("13/11/2026 10am", datetime(2026, 11, 13, 10)),                   # unambiguous d/m
    ("noon on 10 November", datetime(2026, 11, 10, 12)),
])
def test_dates_parse_to_exact_calendar_day(text, expected):
    dt, err = parse(text)
    assert err is None and dt == expected


def test_weekdays_are_derived_from_date():
    assert parse("on 10th November at 5pm")[0].strftime("%A") == "Tuesday"
    assert parse("8 November 10am")[0].strftime("%A") == "Sunday"
    assert parse("day after tomorrow at 5pm")[0].strftime("%A") == "Monday"


def test_year_rollover_and_leap_years():
    assert parse("5 January at 10am")[0] == datetime(2027, 1, 5, 10)      # passed this year
    assert parse("1 November at 10am")[0] == datetime(2027, 11, 1, 10)
    assert parse("29 February 2028 at 10am")[0] == datetime(2028, 2, 29, 10)
    assert parse("29 February at 10am")[0] is None                       # 2027 not leap
    assert "not a valid" in parse("29 February 2027 at 10am")[1]
    assert "already passed" in parse("31 December at 10am", datetime(2026, 12, 31, 12))[1]  # same day, earlier hour
    assert parse("31 December at 3pm", datetime(2026, 12, 31, 12))[0] == datetime(2026, 12, 31, 15)
    assert parse("1 January at 10am", datetime(2026, 12, 31, 12))[0] == datetime(2027, 1, 1, 10)


@pytest.mark.parametrize("text,needle", [
    ("someday soon", "include the date"),
    ("next week", "include the date"),
    ("on 10th November", "include a time"),
    ("on 10th November at 5", "AM/PM"),
    ("10/11/2026 10am", "ambiguous"),
    ("Sunday 10 November at 5pm", "is a Tuesday, not a Sunday"),
    ("tomorrow 10 November at 5pm", "does not match"),
    ("31 November at 10am", "not a valid"),
    ("7 November 2026 at 10am", "already passed"),
    ("today at 9am", "already passed"),
])
def test_unclear_input_asks_for_clarification_never_defaults(text, needle):
    dt, err = parse(text)
    assert dt is None and needle in err


@pytest.fixture()
def frozen(monkeypatch):
    import app.datetime_parse as dp
    monkeypatch.setattr(dp, "business_now", lambda tz=None: NOW)


def _book(text, phone):
    from app.database import SessionLocal
    from app.ai_service import book_appointment_tool
    from app.models import Conversation
    db = SessionLocal()
    conv = Conversation(channel="web"); db.add(conv); db.commit(); db.refresh(conv)
    try:
        return book_appointment_tool(db, conv.id, "Test Visitor", phone, "Checkup", text)
    finally:
        db.close()


def test_booking_confirms_selected_date_and_enforces_rules(client, frozen):
    ok = _book("on 10th November at 5pm", "5550101")
    assert ok["success"] and ok["confirmed_date"] == "2026-11-10"
    assert "Tuesday, 10 November 2026" in ok["message"] and "05:00 PM – 06:00 PM" in ok["message"]
    assert _book("8 November at 10am", "5550102")["error"] == "We are closed on Sundays."
    assert "between 9:00 and 18:00" in _book("9 November at 6pm", "5550103")["error"]
    clash = _book("10 November at 5:30pm", "5550104")
    assert clash["success"] is False  # overlaps the 60-minute slot
    assert "include the date" in _book("whenever", "5550105")["error"]


def test_booking_respects_holiday(client, frozen):
    from app.database import SessionLocal
    from app.ai_service import set_setting
    db = SessionLocal(); set_setting(db, "holiday_dates", "2026-11-10"); db.close()
    assert "holiday" in _book("10 November at 11am", "5550106")["error"]


def test_demo_chat_exact_user_phrases(demo_client, frozen):
    page = demo_client.get("/admin/login")
    tok = re.search(r'csrf_token" value="([^"]+)', page.text).group(1)
    demo_client.post("/admin/demo-login", data={"csrf_token": tok})
    r1 = demo_client.post("/chat", data={"message": "Ahmmad, 555-0199, critical medicine doctor, day after tomorrow at 5pm"}).json()
    assert "Monday, 09 November 2026" in r1["reply"]
    r2 = demo_client.post("/chat", data={"message": "Ahmmad, 555-0198, critical medicine doctor, on 10th November at 5pm"}).json()
    assert "Tuesday, 10 November 2026" in r2["reply"]
    assert "Sunday" not in r1["reply"] + r2["reply"]


def test_business_timezone_not_server_utc():
    from app.datetime_parse import business_now
    a, b = business_now("Asia/Dhaka"), business_now("UTC")
    assert round((a - b).total_seconds() / 3600) == 6


def test_ai_prompt_includes_today_and_forbids_weekday_guessing(client):
    from app.database import SessionLocal
    from app.ai_service import TOOLS, build_system_prompt
    db = SessionLocal()
    try:
        prompt = build_system_prompt(db)
    finally:
        db.close()
    assert "Today is" in prompt and "Never state or compute a weekday" in prompt
    assert "YYYY-MM-DD" in TOOLS[0]["function"]["parameters"]["properties"]["appointment_time_text"]["description"]


@pytest.mark.parametrize("text,expected", [
    ("5pm ,10th november", datetime(2026, 11, 10, 17)),
    ("5 pm, 10 November", datetime(2026, 11, 10, 17)),
    ("17:00 2026-11-10", datetime(2026, 11, 10, 17)),
])
def test_time_before_date(text, expected):
    assert parse(text) == (expected, None)


def test_demo_chat_intro_and_labelled_name_time_before_date(demo_client, frozen):
    page = demo_client.get("/admin/login")
    tok = re.search(r'csrf_token" value="([^"]+)', page.text).group(1)
    demo_client.post("/admin/demo-login", data={"csrf_token": tok})
    msg = "I would like to book an appointment name:Ahmad,555-0197,Medicine doctor,5pm ,10th november"
    reply = demo_client.post("/chat", data={"message": msg}).json()["reply"]
    assert reply.startswith("Appointment confirmed for Ahmad on Tuesday, 10 November 2026, 05:00 PM")
