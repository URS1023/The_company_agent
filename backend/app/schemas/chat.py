from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=300)


class ConversationResponse(BaseModel):
    id: str
    workspace_id: str
    owner_user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CreateRunRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str | None = Field(default=None, max_length=200)
    plugin_version_id: str | None = None


class RunResponse(BaseModel):
    id: str
    workspace_id: str
    conversation_id: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_summary: str | None = None


__all__ = [
    "ConversationResponse",
    "CreateConversationRequest",
    "CreateRunRequest",
    "RunResponse",
]
