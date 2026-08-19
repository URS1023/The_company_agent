from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.files import FileAsset
from backend.app.models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from backend.app.providers.compatible import siliconflow_client
from backend.app.providers.elastic_vector import ElasticsearchVectorStore
from backend.app.schemas.knowledge import (
    AddKnowledgeDocumentRequest,
    CreateKnowledgeBaseRequest,
    KnowledgeBaseResponse,
    KnowledgeDocumentResponse,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from backend.app.services.auth import current_user_context
from backend.app.services.runtime import append_outbox_event

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge"])


def _base_response(base: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(base, from_attributes=True)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[KnowledgeBaseResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.workspace_id == membership.workspace_id,
            (KnowledgeBase.owner_user_id == user.id) | (KnowledgeBase.visibility == "workspace"),
            KnowledgeBase.status == "active",
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )
    return [_base_response(base) for base in rows]


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseResponse:
    user, _, _, membership = await current_user_context(request, db)
    now = utc_now()
    base = KnowledgeBase(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        visibility=payload.visibility,
        created_at=now,
        updated_at=now,
    )
    db.add(base)
    await db.commit()
    return _base_response(base)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_document(
    knowledge_base_id: str,
    payload: AddKnowledgeDocumentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentResponse:
    user, _, _, membership = await current_user_context(request, db)
    base = await db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == membership.workspace_id,
            (KnowledgeBase.owner_user_id == user.id) | (KnowledgeBase.visibility == "workspace"),
        )
    )
    file_asset = await db.scalar(
        select(FileAsset).where(
            FileAsset.id == payload.file_id,
            FileAsset.workspace_id == membership.workspace_id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if not base or not file_asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库或文件不存在")
    existing = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == base.id,
            KnowledgeDocument.file_id == file_asset.id,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件已在知识库中")
    now = utc_now()
    document = KnowledgeDocument(
        id=new_id(),
        workspace_id=membership.workspace_id,
        knowledge_base_id=base.id,
        file_id=file_asset.id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(document)
    await db.flush()
    await append_outbox_event(
        db,
        topic="knowledge.document.created",
        payload={
            "document_id": document.id,
            "knowledge_base_id": base.id,
            "workspace_id": membership.workspace_id,
            "file_id": file_asset.id,
        },
    )
    await db.commit()
    return KnowledgeDocumentResponse(
        id=document.id,
        file_id=document.file_id,
        status=document.status,
        chunk_count=0,
        error_summary=None,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("/{knowledge_base_id}/documents", response_model=list[KnowledgeDocumentResponse])
async def list_documents(
    knowledge_base_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeDocumentResponse]:
    user, _, _, membership = await current_user_context(request, db)
    base = await db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == membership.workspace_id,
            (KnowledgeBase.owner_user_id == user.id) | (KnowledgeBase.visibility == "workspace"),
        )
    )
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    rows = await db.execute(
        select(
            KnowledgeDocument,
            func.count(KnowledgeChunk.id).label("chunk_count"),
        )
        .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.knowledge_base_id == base.id)
        .group_by(KnowledgeDocument.id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    return [
        KnowledgeDocumentResponse(
            id=document.id,
            file_id=document.file_id,
            status=document.status,
            chunk_count=int(chunk_count),
            error_summary=document.error_summary,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
        for document, chunk_count in rows.all()
    ]


@router.post("/{knowledge_base_id}/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    knowledge_base_id: str,
    payload: KnowledgeSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSearchResponse:
    user, _, _, membership = await current_user_context(request, db)
    base = await db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == membership.workspace_id,
            (KnowledgeBase.owner_user_id == user.id) | (KnowledgeBase.visibility == "workspace"),
        )
    )
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if not settings.allow_external_embedding or not settings.siliconflow_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="当前 Workspace 未配置外部 Embedding Provider",
        )
    vectors = await siliconflow_client().embeddings(
        model=settings.siliconflow_embedding_model,
        inputs=[payload.query],
    )
    if not vectors or len(vectors[0]) != settings.siliconflow_embedding_dimensions:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Embedding 维度不匹配")
    hits = await ElasticsearchVectorStore().search(
        workspace_id=membership.workspace_id,
        knowledge_base_id=base.id,
        query_vector=vectors[0],
        k=payload.top_k,
    )
    return KnowledgeSearchResponse(
        query=payload.query,
        hits=[
            KnowledgeSearchHit(
                chunk_id=str(hit.get("chunk_id", "")),
                text=str(hit.get("content", "")),
                score=hit.get("score"),
                location=hit.get("location") or {},
            )
            for hit in hits
        ],
    )


__all__ = ["router"]
