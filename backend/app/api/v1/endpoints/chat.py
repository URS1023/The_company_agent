from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Conversation, Message
from backend.app.schemas.chat import (
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    UpdateConversationRequest,
)
from backend.app.services.audit import record_audit
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


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    user, _, _, membership = await current_user_context(request, db)
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == membership.workspace_id,
            Conversation.owner_user_id == user.id,
            Conversation.archived_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    conversation.title = payload.title.strip() or "新对话"
    conversation.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="conversation.updated",
        resource_type="conversation",
        resource_id=conversation.id,
    )
    await db.commit()
    return ConversationResponse.model_validate(conversation, from_attributes=True)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    user, _, _, membership = await current_user_context(request, db)
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == membership.workspace_id,
            Conversation.owner_user_id == user.id,
            Conversation.archived_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    conversation.archived_at = utc_now()
    conversation.updated_at = utc_now()
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="conversation.archived",
        resource_type="conversation",
        resource_id=conversation.id,
    )
    await db.commit()


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[MessageResponse]:
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
    messages = await db.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.sequence)
    )
    return [MessageResponse.model_validate(row, from_attributes=True) for row in messages]


__all__ = ["router"]
