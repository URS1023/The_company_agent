from fastapi import APIRouter

from backend.app.api.v1.endpoints import health, system

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(system.router)

__all__ = ["router"]
