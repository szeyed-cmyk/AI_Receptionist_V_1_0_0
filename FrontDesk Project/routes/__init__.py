"""HTTP route package.

- ``routes.public``  — public chat / health (intentionally unauthenticated)
- ``routes.auth``    — login, setup, logout (unguarded; setup only when no admin exists)
- ``routes.admin``   — every admin page and mutating admin endpoint (require_admin)
"""
from fastapi import APIRouter

from routes.public import router as public_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router

router = APIRouter()
router.include_router(public_router)
router.include_router(auth_router)
router.include_router(admin_router)

__all__ = ["router"]
