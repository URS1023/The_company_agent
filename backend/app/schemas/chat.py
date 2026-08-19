from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=300)


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class ConversationResponse(BaseModel):
    id: str
    workspace_id: str
    owner_user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    sequence: int
    content: str
    status: str
    parts_json: list[dict] | None = None
    created_at: datetime


class CreateRunRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str | None = Field(default=None, max_length=200)
    plugin_version_id: str | None = None
    file_ids: list[str] = Field(default_factory=list, max_length=20)
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=10)
    data_source_ids: list[str] = Field(default_factory=list, max_length=10)
    artifact_ids: list[str] = Field(default_factory=list, max_length=20)
    connector_version_ids: list[str] = Field(default_factory=list, max_length=20)
    message_parts: list[dict] = Field(default_factory=list, max_length=50)


class RunResponse(BaseModel):
    id: str
    workspace_id: str
    conversation_id: str
    parent_run_id: str | None = None
    plugin_version_id: str | None = None
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_summary: str | None = None


class RunStepResponse(BaseModel):
    id: str
    run_id: str
    sequence: int
    step_type: str
    name: str
    status: str
    input_json: dict | None = None
    output_json: dict | None = None
    error_code: str | None = None
    error_summary: str | None = None
    retry_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ToolCallResponse(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    tool_name: str
    arguments_json: dict
    result_json: dict | None = None
    status: str
    error_code: str | None = None
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ContinueRunRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str | None = Field(default=None, max_length=200)
    message_parts: list[dict] = Field(default_factory=list, max_length=50)


__all__ = [
    "ContinueRunRequest",
    "MessageResponse",
    "ConversationResponse",
    "CreateConversationRequest",
    "UpdateConversationRequest",
    "CreateRunRequest",
    "RunResponse",
    "RunStepResponse",
    "ToolCallResponse",
]
