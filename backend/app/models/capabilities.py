from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.ids import new_id


class SecretRecord(Base):
    __tablename__ = "secrets"
    __table_args__ = (Index("ix_secrets_workspace_id_created_at", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    key_version: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (Index("ix_skills_workspace_id_updated_at", "workspace_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    published_version_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    based_on_version_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (Index("ix_connectors_workspace_id_updated_at", "workspace_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    published_version_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConnectorVersion(Base):
    __tablename__ = "connector_versions"
    __table_args__ = (UniqueConstraint("connector_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    connector_id: Mapped[str] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    based_on_version_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        Index("ix_data_sources_workspace_id_updated_at", "workspace_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    secret_id: Mapped[str | None] = mapped_column(ForeignKey("secrets.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Plugin(Base):
    __tablename__ = "plugins"
    __table_args__ = (Index("ix_plugins_workspace_id_updated_at", "workspace_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    published_version_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PluginVersion(Base):
    __tablename__ = "plugin_versions"
    __table_args__ = (UniqueConstraint("plugin_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    based_on_version_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PluginSkillBinding(Base):
    __tablename__ = "plugin_version_skill_bindings"
    __table_args__ = (UniqueConstraint("plugin_version_id", "skill_version_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    plugin_version_id: Mapped[str] = mapped_column(ForeignKey("plugin_versions.id"), nullable=False)
    skill_version_id: Mapped[str] = mapped_column(ForeignKey("skill_versions.id"), nullable=False)


class PluginToolBinding(Base):
    __tablename__ = "plugin_version_tool_bindings"
    __table_args__ = (UniqueConstraint("plugin_version_id", "connector_version_id"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    plugin_version_id: Mapped[str] = mapped_column(ForeignKey("plugin_versions.id"), nullable=False)
    connector_version_id: Mapped[str] = mapped_column(
        ForeignKey("connector_versions.id"), nullable=False
    )


class PluginResourceBinding(Base):
    __tablename__ = "plugin_version_resource_bindings"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    plugin_version_id: Mapped[str] = mapped_column(ForeignKey("plugin_versions.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(26), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CapabilityTestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (Index("ix_test_runs_workspace_id_created_at", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_workspace_id_created_at", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(nullable=False, default=0)
    storage_key: Mapped[str | None] = mapped_column(String(1000), unique=True)
    external_url: Mapped[str | None] = mapped_column(String(2000))
    sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    parent_artifact_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
