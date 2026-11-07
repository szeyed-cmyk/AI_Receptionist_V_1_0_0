import html
import logging
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import enforce_startup_config, settings

# Fail fast BEFORE any engine/registry exists: weak SECRET_KEY, or DEMO_MODE
# combined with production database/admin/setup/AI credentials.
enforce_startup_config()

from app.database import Base, registry  # noqa: E402
from routes import router  # noqa: E402
from app.security import CsrfError  # noqa: E402

APP_VERSION = "1.0.8"
app = FastAPI(title="FrontDesk AI", version=APP_VERSION)

if settings.demo_mode:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key + "|frontdesk-demo|" + settings.demo_seed,
        session_cookie="frontdesk_demo_session", same_site="lax",
        https_only=bool(settings.https_only), max_age=60 * 60 * 12,
    )


@app.middleware("http")
async def request_safety(request: Request, call_next):
    # Normal production sessions are validated in require_admin as before.
    # Demo code must not assume any order between early dependencies; all
    # real scoped DB access binds to verified demo role + scope in get_db.
    response: Response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    elif request.url.path.startswith("/admin") and response.headers.get("content-type", "").startswith("text/html"):
        # Admin/login/setup pages embed a per-session CSRF token. Never let the
        # browser (Back button, bfcache) or a proxy re-serve a stale copy.
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


_log = logging.getLogger("frontdesk.csrf")
# Pre-authentication forms: send the visitor back to a freshly rendered form
# (new token) with an explanation. No auto-resubmit, so no redirect loop.
_CSRF_RECOVERY = {
    "/admin/login": "/admin/login?error=expired",
    "/admin/demo-login": "/admin/login?error=expired",
    "/admin/setup": "/admin/setup?error=expired",
}


def _safe_back(request: Request) -> str:
    ref = urlsplit(request.headers.get("referer", ""))
    if ref.netloc and ref.netloc != request.url.netloc:
        return "/admin"
    path = ref.path or "/admin"
    return path if path.startswith("/admin") and not path.startswith("//") else "/admin"


@app.exception_handler(CsrfError)
async def csrf_error_handler(request: Request, exc: CsrfError):
    # Log the route only - never tokens, cookies or form values.
    _log.warning("CSRF check failed: %s %s (session_has_token=%s)", request.method,
                 request.url.path, bool(request.session.get("csrf_token")) if "session" in request.scope else False)
    target = _CSRF_RECOVERY.get(request.url.path)
    if target:
        return RedirectResponse(target, status_code=303, headers={"Cache-Control": "no-store"})
    if "text/html" in request.headers.get("accept", ""):
        back = html.escape(_safe_back(request), quote=True)
        return HTMLResponse(
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>Form expired</title></head>"
            "<body style=\"font-family:sans-serif;max-width:32rem;margin:4rem auto\">"
            "<h1>This form has expired</h1><p>The page was opened in another tab or restored "
            "from browser history, so its security token is no longer valid. Nothing was changed.</p>"
            f"<p><a href=\"{back}\">Reload the page</a> and try again.</p></body></html>",
            status_code=403, headers={"Cache-Control": "no-store"},
        )
    return JSONResponse({"detail": exc.detail}, status_code=403)

if not settings.demo_mode:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key, session_cookie="frontdesk_session",
        same_site="lax", https_only=bool(settings.https_only), max_age=60 * 60 * 12,
    )

_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static):
    app.mount("/static", StaticFiles(directory=_static), name="static")
elif os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


def initialise_database():
    """Create tables after route imports registered every model."""
    for db_engine in registry.engines.values():
        Base.metadata.create_all(bind=db_engine)
    if settings.demo_mode:
        from app.demo import ensure_demo_admin, seed_demo_data
        _, Bootstrap = registry.bind()
        with Bootstrap() as db:
            ensure_demo_admin(db)
            seed_demo_data(db)


app.include_router(router)
initialise_database()


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION, "demo_mode": settings.demo_mode}
