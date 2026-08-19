from __future__ import annotations

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class ReadyResponse(BaseModel):
    app: str
    environment: str
    ready: bool
    dependencies: dict[str, DependencyStatus]


__all__ = ["DependencyStatus", "ReadyResponse"]
