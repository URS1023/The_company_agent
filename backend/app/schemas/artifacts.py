from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: str
    run_id: str
    type: str
    name: str
    mime_type: str
    size: int
    status: str
    created_at: datetime


class ArtifactPreviewResponse(BaseModel):
    artifact: ArtifactResponse
    text: str | None = None
    preview_available: bool


class ArtifactInputResponse(BaseModel):
    artifact_id: str
    resource_type: str = "artifact"
    name: str
    mime_type: str
    size: int
    sha256: str | None = None


__all__ = ["ArtifactInputResponse", "ArtifactPreviewResponse", "ArtifactResponse"]
