from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.models.runtime import Run
from backend.app.processors.renderers import (
    DocumentSpec,
    PresentationSpec,
    SpreadsheetSpec,
    render_docx,
    render_pdf,
    render_pptx,
    render_xlsx,
)
from backend.app.schemas.artifacts import ArtifactResponse
from backend.app.schemas.rendering import (
    RenderDocumentRequest,
    RenderPresentationRequest,
    RenderSpreadsheetRequest,
)
from backend.app.services.artifacts import persist_artifact
from backend.app.services.auth import current_user_context

router = APIRouter(prefix="/runs", tags=["rendering"])


async def _owned_run(run_id: str, request: Request, db: AsyncSession) -> tuple[Run, str]:
    user, _, _, membership = await current_user_context(request, db)
    run = await db.scalar(
        select(Run).where(
            Run.id == run_id,
            Run.workspace_id == membership.workspace_id,
            Run.started_by_user_id == user.id,
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run 不存在")
    return run, user.id


@router.post("/{run_id}/render/document", response_model=ArtifactResponse, status_code=201)
async def render_document(
    run_id: str,
    payload: RenderDocumentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    run, user_id = await _owned_run(run_id, request, db)
    content = render_docx(DocumentSpec(**payload.spec))
    artifact = await persist_artifact(
        db,
        run=run,
        owner_user_id=user_id,
        artifact_type="document",
        name=payload.name,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=content,
        metadata={"renderer": "python-docx", "spec": payload.spec},
    )
    await db.commit()
    return ArtifactResponse.model_validate(artifact, from_attributes=True)


@router.post("/{run_id}/render/presentation", response_model=ArtifactResponse, status_code=201)
async def render_presentation(
    run_id: str,
    payload: RenderPresentationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    run, user_id = await _owned_run(run_id, request, db)
    content = render_pptx(PresentationSpec(**payload.spec))
    artifact = await persist_artifact(
        db,
        run=run,
        owner_user_id=user_id,
        artifact_type="presentation",
        name=payload.name,
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        content=content,
        metadata={"renderer": "python-pptx", "spec": payload.spec},
    )
    await db.commit()
    return ArtifactResponse.model_validate(artifact, from_attributes=True)


@router.post("/{run_id}/render/pdf", response_model=ArtifactResponse, status_code=201)
async def render_pdf_artifact(
    run_id: str,
    payload: RenderDocumentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    run, user_id = await _owned_run(run_id, request, db)
    content = render_pdf(DocumentSpec(**payload.spec))
    artifact = await persist_artifact(
        db,
        run=run,
        owner_user_id=user_id,
        artifact_type="pdf",
        name=payload.name,
        mime_type="application/pdf",
        content=content,
        metadata={"renderer": "pymupdf", "spec": payload.spec},
    )
    await db.commit()
    return ArtifactResponse.model_validate(artifact, from_attributes=True)


@router.post("/{run_id}/render/spreadsheet", response_model=ArtifactResponse, status_code=201)
async def render_spreadsheet(
    run_id: str,
    payload: RenderSpreadsheetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    run, user_id = await _owned_run(run_id, request, db)
    content = render_xlsx(SpreadsheetSpec(**payload.spec))
    artifact = await persist_artifact(
        db,
        run=run,
        owner_user_id=user_id,
        artifact_type="spreadsheet",
        name=payload.name,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=content,
        metadata={"renderer": "openpyxl", "spec": payload.spec},
    )
    await db.commit()
    return ArtifactResponse.model_validate(artifact, from_attributes=True)


__all__ = ["router"]
