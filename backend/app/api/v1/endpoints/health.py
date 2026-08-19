from __future__ import annotations

from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.core.database import database_ping
from backend.app.core.external_services import elasticsearch_ping, redis_ping
from backend.app.schemas.health import DependencyStatus, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@router.get("/health/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    mysql_ok, mysql_detail = await database_ping()
    redis_ok, redis_detail = await redis_ping()
    elastic_ok, elastic_detail = await elasticsearch_ping()
    dependencies = {
        "mysql": DependencyStatus(ok=mysql_ok, detail=mysql_detail),
        "redis": DependencyStatus(ok=redis_ok, detail=redis_detail),
        "elasticsearch": DependencyStatus(ok=elastic_ok, detail=elastic_detail),
    }
    return ReadyResponse(
        app=settings.app_name,
        environment=settings.app_env,
        ready=all(item.ok for item in dependencies.values()),
        dependencies=dependencies,
    )


__all__ = ["router"]
