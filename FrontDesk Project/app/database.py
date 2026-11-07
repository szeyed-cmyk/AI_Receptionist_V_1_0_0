import hashlib
import os

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.requests import Request
from app.config import settings

Base = declarative_base()


class DatabaseRegistry:
    def __init__(self):
        self.engines = {}
        self.sessions = {}
        self.demo_scopes = set()
        if settings.demo_mode:
            seed = "".join(c for c in settings.demo_seed if c.isalnum() or c in "-_")[:48] or "review-demo-v1"
            settings.database_url = f"sqlite:///./data/demo-{seed}/_bootstrap.db"
            settings.business_name = "Lumen Dental Studio"
            settings.admin_username = "demo-admin"
            # enforce_demo_isolation() has already refused to start if any
            # admin/setup/AI credential was configured; these are belt-and-braces.
            settings.admin_password = ""
            settings.setup_token = ""
            settings.ai_api_key = ""
            settings.ai_base_url = ""
            settings.ai_model = "local-demo"

    def _create_engine(self, url):
        if url.startswith("sqlite:///"):
            path = url[len("sqlite:///"):]
            if path.startswith("./"):
                path = path[2:]
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
        e = create_engine(url, connect_args={"check_same_thread": False})
        # SQLite disables foreign keys per connection by default; enable them on
        # EVERY new pooled connection so ON DELETE CASCADE / SET NULL apply.
        @event.listens_for(e, "connect")
        def _pragmas(dbapi_connection, record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        return e

    def can_create_demo(self, scope: str) -> bool:
        """Bounded demo capacity; login can fail without touching production."""
        return scope in self.demo_scopes or len(self.demo_scopes) < max(1, min(settings.demo_max_sessions, 1000))

    def bind(self, scope: str | None = None):
        if settings.demo_mode and scope:
            opaque = hashlib.sha256(f"{settings.demo_seed}|{scope}".encode()).hexdigest()[:40]
            seed = "".join(c for c in settings.demo_seed if c.isalnum() or c in "-_")[:48] or "demo"
            if scope not in self.demo_scopes and not self.can_create_demo(scope):
                raise HTTPException(status_code=503, detail="Demo sandboxes are full. Please try later.")
            self.demo_scopes.add(scope)
            url = f"sqlite:///./data/demo-{seed}/{opaque}.db"
        else:
            url = settings.database_url
        if url not in self.engines:
            self.engines[url] = self._create_engine(url)
            self.sessions[url] = sessionmaker(autocommit=False, autoflush=False, bind=self.engines[url])
            Base.metadata.create_all(bind=self.engines[url])
        return self.engines[url], self.sessions[url]


registry = DatabaseRegistry()
engine, SessionLocal = registry.bind()


def bind_for_session(scope=None):
    return registry.bind(scope)


def get_db(request: Request):
    """Resolve the session after guard execution, keeping production separate."""
    # Dependencies run after SessionMiddleware inside the ASGI stack.
    scope = request.session.get("demo_scope") if settings.demo_mode else None
    if settings.demo_mode and not scope:
        # Fallback for routes declared before custom wrappers: ensure ordinary
        # public chat can only ever reach local-demo storage, never production.
        import secrets
        scope = secrets.token_urlsafe(24)
        request.session["demo_scope"] = scope
        request.session.setdefault("demo_visitor", True)

    factory = registry.bind(scope)[1] if settings.demo_mode else SessionLocal
    db = factory()
    if settings.demo_mode and scope:
        from app.demo import ensure_demo_admin, seed_demo_data
        ensure_demo_admin(db)
        seed_demo_data(db)
    try:
        yield db
    finally:
        db.close()
