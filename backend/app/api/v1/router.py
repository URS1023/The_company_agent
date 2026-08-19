from fastapi import APIRouter

from backend.app.api.v1.endpoints import (
    admin,
    auth,
    chat,
    files,
    health,
    knowledge,
    runs,
    system,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(chat.router)
router.include_router(runs.router)
router.include_router(files.router)
router.include_router(knowledge.router)

__all__ = ["router"]
