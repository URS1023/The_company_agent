from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.storage import LocalFileStorage, StorageError
from backend.app.models.capabilities import Artifact
from backend.app.schemas.artifacts import ArtifactPreviewResponse, ArtifactResponse
from backend.app.services.auth import current_user_context

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse.model_validate(artifact, from_attributes=True)


async def _authorized_artifact(artifact_id: str, request: Request, db: AsyncSession) -> Artifact:
    user, _, _, membership = await current_user_context(request, db)
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.workspace_id == membership.workspace_id,
            Artifact.owner_user_id == user.id,
            Artifact.status != "deleted",
        )
    )
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact 不存在")
    return artifact


@router.get("", response_model=list[ArtifactResponse])
async def list_artifacts(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[ArtifactResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Artifact)
        .where(
            Artifact.workspace_id == membership.workspace_id,
            Artifact.owner_user_id == user.id,
            Artifact.status != "deleted",
        )
        .order_by(Artifact.created_at.desc())
        .limit(100)
    )
    return [_response(row) for row in rows]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> ArtifactResponse:
    return _response(await _authorized_artifact(artifact_id, request, db))


@router.get("/{artifact_id}/preview", response_model=ArtifactPreviewResponse)
async def preview_artifact(
    artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> ArtifactPreviewResponse:
    artifact = await _authorized_artifact(artifact_id, request, db)
    text: str | None = None
    preview_available = False
    if artifact.storage_key and artifact.mime_type.startswith(("text/", "application/json")):
        try:
            text = (
                LocalFileStorage()
                .get_bytes(artifact.storage_key)
                .decode("utf-8", errors="replace")[:50_000]
            )
            preview_available = True
        except StorageError:
            preview_available = False
    return ArtifactPreviewResponse(
        artifact=_response(artifact), text=text, preview_available=preview_available
    )


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    artifact = await _authorized_artifact(artifact_id, request, db)
    if not artifact.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact 没有本地文件")
    try:
        content = LocalFileStorage().get_bytes(artifact.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact 文件不存在"
        ) from exc
    disposition_name = artifact.name.replace('"', "_")
    return Response(
        content=content,
        media_type=artifact.mime_type
        or mimetypes.guess_type(artifact.name)[0]
        or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{disposition_name}"'},
    )


__all__ = ["router"]
