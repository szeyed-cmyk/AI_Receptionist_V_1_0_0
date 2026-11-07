"""Regression tests for the v1.0.6 Vibe96 audit-warning fixes."""
from __future__ import annotations

import inspect
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
GOOD_KEY = secrets.token_urlsafe(48)

CLEAN_ENV_KEYS = (
    "DATABASE_URL", "SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "SETUP_TOKEN",
    "AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "DEMO_MODE", "DEMO_SEED", "FRONTDESK_TESTING", "RENDER",
)


def _start(tmp_path, **env):
    """Import the real app in a fresh interpreter (real startup path, no .env)."""
    base = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV_KEYS}
    base.update({"PYTHONPATH": str(PROJECT), "HTTPS_ONLY": "false"})
    base.update(env)
    return subprocess.run(
        [sys.executable, "-c", "import app; print('STARTED')"],
        cwd=tmp_path, env=base, capture_output=True, text=True, timeout=60,
    )


# --- SECRET_KEY --------------------------------------------------------------

def test_env_examples_have_blank_secret_and_generation_comment():
    for path in (ROOT / ".env.example", PROJECT / ".env.example"):
        text = path.read_text()
        assert re.search(r"^SECRET_KEY=\s*$", text, re.M), path
        assert "secrets.token_urlsafe(48)" in text, path
        assert "change-this" not in text, path
    assert (ROOT / ".env.example").read_text() == (PROJECT / ".env.example").read_text()


@pytest.mark.parametrize("key", ["", "change-this-to-a-long-random-string-in-production", "changeme", "short-key-123"])
@pytest.mark.parametrize("demo", ["false", "true"])
def test_insecure_secret_key_refused_at_startup_in_all_modes(tmp_path, key, demo):
    r = _start(tmp_path, SECRET_KEY=key, DEMO_MODE=demo)
    assert r.returncode != 0 and "STARTED" not in r.stdout
    assert "SECRET_KEY" in r.stderr


def test_strong_secret_key_starts(tmp_path):
    r = _start(tmp_path, SECRET_KEY=GOOD_KEY, DATABASE_URL=f"sqlite:///{tmp_path}/p.db")
    assert r.returncode == 0, r.stderr
    assert "STARTED" in r.stdout


def test_testing_bypass_is_ignored_on_render(tmp_path):
    r = _start(tmp_path, SECRET_KEY="", FRONTDESK_TESTING="1", RENDER="true")
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr


# --- DEMO_MODE isolation -------------------------------------------------------

@pytest.mark.parametrize("name,value", [
    ("DATABASE_URL", "postgresql://u:p@db.invalid/prod"),
    ("DATABASE_URL", "sqlite:///./data/ai_receptionist.db"),
    ("ADMIN_USERNAME", "owner"),
    ("ADMIN_PASSWORD", "real-password-123"),
    ("SETUP_TOKEN", "setup-token-value"),
    ("AI_API_KEY", "provider-key-value"),
    ("AI_BASE_URL", "https://api.invalid/v1"),
])
def test_demo_mode_refuses_production_configuration(tmp_path, name, value):
    # Even the pytest bypass must not relax the demo isolation check.
    r = _start(tmp_path, SECRET_KEY=GOOD_KEY, DEMO_MODE="true", FRONTDESK_TESTING="1", **{name: value})
    assert r.returncode != 0 and "STARTED" not in r.stdout
    assert "DEMO_MODE=true cannot start" in r.stderr and name in r.stderr
    assert not list(tmp_path.rglob("*.db")), "no database may be created before refusal"


@pytest.mark.parametrize("dsn", ["", "sqlite:///./data/demo-review-v1/_bootstrap.db"])
def test_demo_mode_starts_with_dedicated_sandbox_only(tmp_path, dsn):
    r = _start(tmp_path, SECRET_KEY=GOOD_KEY, DEMO_MODE="true", DEMO_SEED="review-v1", DATABASE_URL=dsn)
    assert r.returncode == 0, r.stderr
    assert list((tmp_path / "data").glob("demo-review-v1/*.db"))


# --- /admin/setup ----------------------------------------------------------------

def test_setup_token_compare_is_constant_time():
    from app import security
    src = inspect.getsource(security.require_setup_token)
    assert "secrets.compare_digest" in src


def test_setup_post_is_rate_limited(fresh_client):
    page = fresh_client.get("/admin/setup")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    codes = []
    for _ in range(7):
        r = fresh_client.post("/admin/setup", data={
            "username": "admin", "password": "goodpass1", "confirm_password": "goodpass1",
            "setup_token": "wrong", "csrf_token": token,
        }, follow_redirects=False)
        codes.append(r.status_code)
    assert codes[:5] == [403] * 5
    assert codes[5:] == [429, 429]


# --- search / delete --------------------------------------------------------------

def test_search_is_bound_and_wildcards_escaped(admin_client):
    from app.database import SessionLocal
    from app.models import KnowledgeItem
    from app.web import LIKE_ESCAPE, like_term

    db = SessionLocal()
    db.add_all([KnowledgeItem(question="Opening hours", answer="9 to 6"),
                KnowledgeItem(question="Parking", answer="Free")])
    db.commit()
    stmt = db.query(KnowledgeItem).filter(KnowledgeItem.question.ilike(like_term("x' OR 1=1 --"), escape=LIKE_ESCAPE)).statement
    compiled = stmt.compile()
    assert "OR 1=1" not in str(compiled) and compiled.params
    db.close()
    page = admin_client.get("/admin/knowledge", params={"q": "%"})
    assert page.status_code == 200
    assert "Opening hours" not in page.text and "Parking" not in page.text
    page = admin_client.get("/admin/knowledge", params={"q": "' OR 1=1 --"})
    assert page.status_code == 200 and "Parking" not in page.text
    assert "Parking" in admin_client.get("/admin/knowledge", params={"q": "park"}).text


def test_mutations_load_single_row_by_primary_key():
    from app import app as _app  # noqa: F401  (import order: app package first)
    from routes.admin import conversations, knowledge, appointments
    for module, model in ((knowledge, "KnowledgeItem"), (conversations, "Conversation"), (appointments, "Appointment")):
        src = inspect.getsource(module)
        assert f"db.get({model}," in src
        assert ".delete(synchronize_session" not in src and not re.search(r"\btext\(", src)
    for fn in (knowledge.knowledge_delete, knowledge.knowledge_update, conversations.conversation_delete):
        src = inspect.getsource(fn)
        assert "verify_csrf" in src and "demo_blocks_mutation" in src and "require_admin" in src


# --- schema & foreign keys ------------------------------------------------------

def _describe(conn):
    out = {}
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in sorted(tables):
        cols = sorted((r[1], r[3], r[5]) for r in conn.execute(f"PRAGMA table_info({t})"))
        fks = sorted((r[2], r[3], r[4], r[6]) for r in conn.execute(f"PRAGMA foreign_key_list({t})"))
        idx = {}
        for r in conn.execute(f"PRAGMA index_list({t})"):
            cols_i = tuple(c[2] for c in conn.execute(f"PRAGMA index_info('{r[1]}')"))
            idx[cols_i] = bool(r[2])
        out[t] = (cols, fks, sorted(idx.items()))
    return out


def test_schema_sql_matches_sqlalchemy_models(tmp_path):
    from sqlalchemy import create_engine
    from app.database import Base
    import app.models  # noqa: F401

    sql_db = tmp_path / "sql.db"
    with sqlite3.connect(sql_db) as conn:
        conn.executescript((ROOT / "database" / "schema.sql").read_text())
    orm_db = tmp_path / "orm.db"
    eng = create_engine(f"sqlite:///{orm_db}")
    Base.metadata.create_all(eng)
    eng.dispose()
    with sqlite3.connect(sql_db) as a, sqlite3.connect(orm_db) as b:
        da, db_ = _describe(a), _describe(b)
    assert set(da) == set(db_)
    for table in da:
        cols_a, fks_a, idx_a = da[table]
        cols_b, fks_b, idx_b = db_[table]
        assert [c[0] for c in cols_a] == [c[0] for c in cols_b], table
        assert [(c[0], c[1], c[2]) for c in cols_a] == [(c[0], c[1], c[2]) for c in cols_b], table
        assert fks_a == fks_b, table
        assert idx_a == idx_b, table
    assert ("conversations", "conversation_id", "id", "CASCADE") in da["messages"][1]
    assert ("conversations", "conversation_id", "id", "SET NULL") in da["appointments"][1]


def test_foreign_keys_enabled_on_every_connection(client):
    from app.database import engine
    seen = []
    for _ in range(3):
        with engine.connect() as conn:
            seen.append(conn.exec_driver_sql("PRAGMA foreign_keys").scalar())
    raw = engine.raw_connection()  # a brand-new DBAPI connection from the pool
    try:
        seen.append(raw.cursor().execute("PRAGMA foreign_keys").fetchone()[0])
    finally:
        raw.close()
    assert seen == [1, 1, 1, 1]


# --- structure ---------------------------------------------------------------------

def test_chat_max_length_reads_settings():
    from routes import public
    from app.config import settings
    src = inspect.getsource(public)
    assert "max_length=2000" not in src
    assert "max_length=settings.chat_message_max_length" in src
    assert settings.chat_message_max_length == 2000


def test_single_template_context_builder_and_split_admin_router():
    route_src = "".join(p.read_text() for p in (PROJECT / "routes").rglob("*.py"))
    assert "def _tpl" not in route_src
    assert "def demo_created" not in route_src and "def demo_can_mutate" not in route_src
    assert not (PROJECT / "routes" / "admin.py").exists()
    from app import app as _app  # noqa: F401
    from app.security import require_admin
    from routes.admin import appointments, conversations, dashboard, knowledge, settings
    for module in (appointments, conversations, dashboard, knowledge, settings):
        deps = [d.dependency for d in module.router.dependencies]
        assert require_admin in deps, module.__name__
        assert len(module.__file__ and Path(module.__file__).read_text().splitlines()) < 120


def test_single_runtime_tree_and_single_dockerfile():
    assert (ROOT / "Dockerfile").is_file()
    assert not (PROJECT / "Dockerfile").exists()
    assert not (PROJECT / ".dockerignore").exists()
    assert not (ROOT / "main.py").exists() and not (ROOT / "app").exists() and not (ROOT / "routes").exists()
    assert not (ROOT / "requirements.txt").exists() and not (ROOT / "requirements.lock").exists()


def test_docs_state_prerequisites_and_compose_order():
    text = (ROOT / "HowToSetup.md").read_text()
    assert "Python 3.12" in text and "SQLite 3.35" in text
    a = text.index("cp .env.example .env")
    b = text.index("SECRET_KEY=", a)
    c = text.index("docker compose up --build", b)
    assert a < b < c
    for doc in ("CLAUDE.md", "HowToSetup.md", "README.md"):
        for ref in re.findall(r"`([\w ./-]*tests/)`", (ROOT / doc).read_text()):
            assert (ROOT / ref.strip("/")).exists() or (PROJECT / "tests").exists()
    assert (ROOT / "tests").is_dir() and (PROJECT / "tests").is_dir()
