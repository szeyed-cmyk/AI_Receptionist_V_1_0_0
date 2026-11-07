"""Per-session demo write allowlist (moved out of the admin controller).

Each demo reviewer already gets a private SQLite sandbox. On top of that, edit
and delete handlers only accept rows that THIS signed session created, so the
seeded fixtures cannot be removed and IDs cannot be guessed across sessions.
"""
from __future__ import annotations

from starlette.requests import Request

from app.config import settings

ALLOWED_DEMO_CHANGES_KEY = "_demo_allowed_changes"


def is_demo_session(request: Request) -> bool:
    return bool(settings.demo_mode and request.session.get("demo_session"))


def demo_writes(request: Request) -> dict:
    return request.session.get(ALLOWED_DEMO_CHANGES_KEY) or {}


def demo_created(request: Request, kind: str, item_id: int, description: str) -> None:
    """Record a row created through this specific sandbox session."""
    if not is_demo_session(request):
        return
    changes = demo_writes(request)
    entries = list(changes.get(kind, []))
    entries.append({"id": item_id, "description": description[:140]})
    # Keep Starlette's signed client-side session bounded.
    changes[kind] = entries[-25:]
    request.session[ALLOWED_DEMO_CHANGES_KEY] = changes


def demo_can_mutate(request: Request, kind: str, item_id: int) -> bool:
    return any(entry.get("id") == item_id for entry in demo_writes(request).get(kind, []))


def demo_blocks_mutation(request: Request, kind: str, item_id: int) -> bool:
    """True when demo mode is on and this session did not create the row."""
    return settings.demo_mode and not demo_can_mutate(request, kind, item_id)
