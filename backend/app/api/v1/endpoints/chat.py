from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Conversation
from backend.app.schemas.chat import ConversationResponse, CreateConversationRequest
from backend.app.services.auth import current_user_context

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    request: Request, db: AsyncSession = Depends(get_db)
) -> list[ConversationResponse]:
    user, _, _, membership = await current_user_context(request, db)
    rows = await db.scalars(
        select(Conversation)
        .where(
            Conversation.workspace_id == membership.workspace_id,
            Conversation.owner_user_id == user.id,
            Conversation.archived_at.is_(None),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    return [ConversationResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    user, _, _, membership = await current_user_context(request, db)
    now = utc_now()
    conversation = Conversation(
        id=new_id(),
        workspace_id=membership.workspace_id,
        owner_user_id=user.id,
        title=payload.title.strip() or "新对话",
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.commit()
    return ConversationResponse.model_validate(conversation, from_attributes=True)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    user, _, _, membership = await current_user_context(request, db)
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == membership.workspace_id,
            Conversation.owner_user_id == user.id,
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return ConversationResponse.model_validate(conversation, from_attributes=True)


__all__ = ["router"]
