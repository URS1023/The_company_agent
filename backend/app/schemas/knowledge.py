from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: str = Field(default="private", pattern="^(private|workspace)$")


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime


class AddKnowledgeDocumentRequest(BaseModel):
    file_id: str


class KnowledgeDocumentResponse(BaseModel):
    id: str
    file_id: str
    status: str
    chunk_count: int = 0
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=8, ge=1, le=50)


class KnowledgeSearchHit(BaseModel):
    chunk_id: str
    text: str
    score: float | None = None
    location: dict = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    hits: list[KnowledgeSearchHit]


__all__ = [
    "AddKnowledgeDocumentRequest",
    "CreateKnowledgeBaseRequest",
    "KnowledgeBaseResponse",
    "KnowledgeDocumentResponse",
    "KnowledgeSearchHit",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResponse",
]
