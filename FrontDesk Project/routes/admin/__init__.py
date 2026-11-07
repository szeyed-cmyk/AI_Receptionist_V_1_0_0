"""Admin routes, split by feature. Every sub-router is guarded by require_admin.

- dashboard      -> /admin
- knowledge      -> /admin/knowledge...
- settings       -> /admin/settings, /admin/change-password
- appointments   -> /admin/appointments...
- conversations  -> /admin/conversations...
"""
from fastapi import APIRouter, Depends

from app.security import require_admin
from routes.admin import appointments, conversations, dashboard, knowledge, settings

router = APIRouter(dependencies=[Depends(require_admin)])
for _module in (dashboard, knowledge, settings, appointments, conversations):
    router.include_router(_module.router)

__all__ = ["router"]
