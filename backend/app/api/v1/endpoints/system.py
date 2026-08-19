from __future__ import annotations

from fastapi import APIRouter

from backend.app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/config")
async def config_summary() -> dict[str, object]:
    """Expose safe capability/config metadata; never return secrets."""

    return {
        "environment": settings.app_env,
        "chat_provider": "agnes",
        "chat_model": settings.agnes_model,
        "vision_provider": "siliconflow",
        "vision_model": settings.siliconflow_vision_model,
        "embedding_provider": "siliconflow",
        "embedding_model": settings.siliconflow_embedding_model,
        "embedding_dimensions": settings.siliconflow_embedding_dimensions,
        "native_dev_arbitrary_code_execution": False,
        "external_processing": {
            "chat": settings.allow_external_chat,
            "vision": settings.allow_external_vision,
            "embedding": settings.allow_external_embedding,
        },
    }


__all__ = ["router"]
