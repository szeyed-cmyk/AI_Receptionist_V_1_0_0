"""Every mutating route is either public-allowlisted or rejects unauthenticated callers."""
from __future__ import annotations

PUBLIC_MUTATING_ALLOWLIST = {
    ("POST", "/chat"),
    ("POST", "/admin/login"),
    ("POST", "/admin/setup"),
}


def _iter_routes(routes, prefix: str = ""):
    """Walk FastAPI/Starlette route trees including FastAPI 0.162 _IncludedRouter."""
    for route in routes:
        # Nested include wrapper (FastAPI >= 0.162)
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_routes(getattr(original, "routes", []) or [], prefix)
            continue

        path = getattr(route, "path", None) or ""
        methods = getattr(route, "methods", None)
        children = getattr(route, "routes", None)
        full = (prefix + path) if path else prefix
        if methods:
            yield full, set(methods)
        if children:
            yield from _iter_routes(children, full)


def test_mutating_routes_require_auth_or_are_allowlisted(client):
    from app import app as fastapi_app

    mutating = []
    for path, methods in _iter_routes(fastapi_app.routes):
        for method in methods:
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                mutating.append((method, path))

    assert mutating, "expected at least one mutating route"

    for method, path in mutating:
        if (method, path) in PUBLIC_MUTATING_ALLOWLIST:
            continue
        call_path = path
        for name in ("item_id", "appt_id", "conv_id"):
            call_path = call_path.replace("{" + name + "}", "1")
        r = client.request(method, call_path, data={}, follow_redirects=False)
        assert r.status_code in {303, 401, 403, 404, 405, 422}, (
            f"{method} {path} returned {r.status_code} without auth"
        )
        if r.status_code == 303:
            loc = r.headers.get("location", "")
            assert "/admin/login" in loc or "/admin/setup" in loc, (
                f"{method} {path} redirected to unexpected {loc}"
            )


def test_admin_router_declares_require_admin_dependency():
    """Scanner-friendly: the admin APIRouter lists require_admin in dependencies."""
    from routes.admin import router
    from app.security import require_admin

    dep_calls = [getattr(d, "dependency", None) for d in (router.dependencies or [])]
    assert require_admin in dep_calls
