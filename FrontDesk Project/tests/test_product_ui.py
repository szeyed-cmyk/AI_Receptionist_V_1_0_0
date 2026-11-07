"""Landing, local assets, metrics and traditional production admin mutations."""
from __future__ import annotations

import re
from datetime import datetime, time


def csrf(client, path="/admin/settings"):
    page = client.get(path)
    assert page.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, f"CSRF token missing from {path}"
    return match.group(1)


def test_landing_and_local_assets(client):
    landing = client.get("/")
    assert landing.status_code == 200
    assert 'href="/admin/login"' in landing.text
    assert 'Live demo' in landing.text
    assert 'id="features"' in landing.text and 'id="benefits"' in landing.text
    assert '/static/04-chat-greeting.jpg' in landing.text
    assert 'testimonial' not in landing.text.lower()
    assert landing.text.count('placehold') == 0
    assert '/static/admin-demo-dashboard.png' in landing.text
    assert 'admin demo dashboard showing appointment metrics' in landing.text.lower()
    assert 'Actual admin demo dashboard' in landing.text
    for asset in ("04-chat-greeting.jpg", "admin-demo-dashboard.png", "app.css", "vendor/tailwindcss.js", "chat.js"):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200, asset
        assert len(response.content) > 100, asset
    assert client.get("/chat").status_code == 200
    assert client.get("/health").json()["version"] == "1.0.8"
    assert landing.headers["x-frame-options"] == "DENY"


def test_demo_button_and_endpoint_not_exposed_in_production(client):
    page = client.get("/admin/login")
    assert page.status_code == 200
    assert "/admin/demo-login" not in page.text
    response = client.post("/admin/demo-login", data={"csrf_token": "any"}, follow_redirects=False)
    assert response.status_code == 404


def test_dashboard_uses_real_database_data(client, admin_client):
    from app.database import SessionLocal
    from app.models import Appointment, Conversation, KnowledgeItem, Message
    db = SessionLocal()
    now = datetime.now()
    today_at_ten = datetime.combine(now.date(), time(10, 0))
    conv = Conversation(channel="web", customer_name="Metric Visitor", visitor_token="metric")
    db.add(conv)
    db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content="Could I visit?"))
    db.add(Appointment(customer_name="Metric Visitor", customer_phone="555-0180", service="Test Service", conversation_id=conv.id, appointment_time=today_at_ten, duration_minutes=60, status="confirmed"))
    db.add(KnowledgeItem(question="Metric question", answer="Metric answer", category="Testing"))
    db.commit()
    db.close()
    page = admin_client.get("/admin")
    assert page.status_code == 200
    assert "Metric Visitor" in page.text
    assert "Test Service" in page.text
    assert "Conversation activity" in page.text
    assert 'Today’s appointments' in page.text


def test_admin_smoke_search_and_management(client, admin_client):
    for path in ("/admin", "/admin/knowledge", "/admin/appointments", "/admin/conversations", "/admin/settings"):
        r = admin_client.get(path)
        assert r.status_code == 200, path
        assert "/static/vendor/tailwindcss.js" in r.text
        assert "cdn.tailwindcss.com" not in r.text
    token = csrf(admin_client, "/admin/knowledge")
    r = admin_client.post("/admin/knowledge", data={"question": "Can I test a question?", "answer": "Test answer", "category": "Testing", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    from app.database import SessionLocal
    from app.models import KnowledgeItem
    db = SessionLocal()
    item = db.query(KnowledgeItem).filter_by(question="Can I test a question?").one()
    item_id = item.id
    db.close()
    assert "Test answer" in admin_client.get("/admin/knowledge?q=Test").text
    r = admin_client.get(f"/admin/knowledge/{item_id}/edit")
    assert r.status_code == 200 and "Test answer" in r.text
    r = admin_client.post(f"/admin/knowledge/{item_id}/edit", data={"question": "Updated question", "answer": "Updated answer", "category": "Testing", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    db = SessionLocal()
    item = db.get(KnowledgeItem, item_id)
    assert item.question == "Updated question" and item.is_active is False
    db.close()
    r = admin_client.post(f"/admin/knowledge/{item_id}/delete", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    assert admin_client.get(f"/admin/knowledge/{item_id}/edit").status_code == 404


def test_appointment_status_allowlist_and_csrf(client, admin_client):
    from app.database import SessionLocal
    from app.models import Appointment
    db = SessionLocal()
    row = Appointment(customer_name="Status Tester", appointment_time=datetime.now(), status="confirmed")
    db.add(row)
    db.commit()
    row_id = row.id
    db.close()
    token = csrf(admin_client)
    r = admin_client.post(f"/admin/appointments/{row_id}/status", data={"status": "hacked-admin", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 422
    r = admin_client.post(f"/admin/appointments/{row_id}/status", data={"status": "completed"}, follow_redirects=False)
    assert r.status_code == 403
    r = admin_client.post(f"/admin/appointments/{row_id}/status", data={"status": "completed", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    db = SessionLocal()
    assert db.get(Appointment, row_id).status == "completed"
    db.close()


def test_settings_validation_does_not_save_invalid_hours(admin_client):
    token = csrf(admin_client)
    data = {"business_name": "Test Clinic", "ai_base_url": "", "ai_api_key": "", "ai_model": "", "opening_hour": "19", "closing_hour": "9", "closed_days": "sunday", "holiday_dates": "", "csrf_token": token}
    r = admin_client.post("/admin/settings", data=data, follow_redirects=False)
    assert r.status_code == 303 and "error=schedule" in r.headers["location"]
    from app.database import SessionLocal
    from app.ai_service import get_setting
    db = SessionLocal()
    assert get_setting(db, "opening_hour") == "9"
    db.close()
