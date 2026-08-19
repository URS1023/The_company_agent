from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import router as v1_router
from backend.app.core.config import settings
from backend.app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key", "X-CSRF-Token"],
)


@app.middleware("http")
async def same_origin_guard(request, call_next):
    """Reject cross-site state-changing requests while keeping local CLI/API use."""

    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith(
        "/api/"
    ):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in {
            value.rstrip("/") for value in settings.web_origins
        }:
            from starlette.responses import JSONResponse

            return JSONResponse(status_code=403, content={"detail": "Origin 不被允许"})
    return await call_next(request)


app.include_router(v1_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs"}


def run() -> None:
    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "native-dev",
    )


__all__ = ["app", "run"]
