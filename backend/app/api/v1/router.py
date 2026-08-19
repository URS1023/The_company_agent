from fastapi import APIRouter

from backend.app.api.v1.endpoints import admin, auth, health, system

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(admin.router)

__all__ = ["router"]
