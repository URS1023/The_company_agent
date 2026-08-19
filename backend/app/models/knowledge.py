from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.ids import new_id


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        Index(
            "ix_knowledge_bases_workspace_id_created_at",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("knowledge_base_id", "file_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False, default="native-0.1")
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_document_id_ordinal", "document_id", "ordinal"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(nullable=True)
    elasticsearch_document_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
