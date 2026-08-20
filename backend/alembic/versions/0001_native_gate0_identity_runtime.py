"""Create native Gate 0 identity and runtime tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_native_gate0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "organization_id", sa.String(26), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_workspaces_organization_id", "organization_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("username_normalized", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "username_normalized"),
    )
    op.create_table(
        "local_credentials",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "auth_identity_id", sa.String(26), sa.ForeignKey("auth_identities.id"), nullable=False
        ),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("temporary_password_expires_at", sa.DateTime(timezone=True)),
        sa.Column("failed_attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("credential_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("auth_identity_id"),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "organization_id", sa.String(26), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id"),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("credential_version", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_digest"),
        sa.Index("ix_sessions_user_id", "user_id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Index("ix_conversations_workspace_id_updated_at", "workspace_id", "updated_at"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(26), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "sequence"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(26), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("started_by_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        # Plugin versions are declared later; the ORM provides the relation.
        sa.Column("plugin_version_id", sa.String(26)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(200)),
        sa.Column("effective_config_hash", sa.String(128)),
        sa.Column("model_usage", sa.JSON),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Index("ix_runs_workspace_id_created_at", "workspace_id", "created_at"),
    )
    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_run_events_run_id_id", "run_id", "id"),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Index("ix_outbox_events_unpublished", "published_at", "created_at"),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        # Keep the unique utf8mb4 key within MySQL's 3072-byte index limit.
        # The generated workspace path plus a user filename stays below this
        # bound while the full content remains in local storage metadata.
        sa.Column("storage_key", sa.String(768), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("storage_key"),
        sa.Index("ix_files_workspace_id_created_at", "workspace_id", "created_at"),
    )
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_knowledge_bases_workspace_id_created_at", "workspace_id", "created_at"),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "knowledge_base_id", sa.String(26), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("file_id", sa.String(26), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("knowledge_base_id", "file_id"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "knowledge_base_id", sa.String(26), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column(
            "document_id", sa.String(26), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("location", sa.JSON, nullable=False),
        sa.Column("embedding_status", sa.String(32), nullable=False),
        sa.Column("embedding_model", sa.String(200)),
        sa.Column("embedding_dimensions", sa.Integer),
        sa.Column("elasticsearch_document_id", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_knowledge_chunks_document_id_ordinal", "document_id", "ordinal"),
    )
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("ciphertext", sa.Text, nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Index("ix_secrets_workspace_id_created_at", "workspace_id", "created_at"),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_skills_workspace_id_updated_at", "workspace_id", "updated_at"),
    )
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("skill_id", sa.String(26), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("based_on_version_id", sa.String(26)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("skill_id", "version_number"),
    )
    op.create_table(
        "connectors",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_connectors_workspace_id_updated_at", "workspace_id", "updated_at"),
    )
    op.create_table(
        "connector_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("connector_id", sa.String(26), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("based_on_version_id", sa.String(26)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("connector_id", "version_number"),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("connector_id", sa.String(26), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_tools_workspace_id_name", "workspace_id", "name"),
    )
    op.create_table(
        "tool_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tool_id", sa.String(26), sa.ForeignKey("tools.id"), nullable=False),
        sa.Column(
            "connector_version_id",
            sa.String(26),
            sa.ForeignKey("connector_versions.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tool_id", "version_number"),
    )
    op.create_table(
        "connector_tool_bindings",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "connector_version_id",
            sa.String(26),
            sa.ForeignKey("connector_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "tool_version_id", sa.String(26), sa.ForeignKey("tool_versions.id"), nullable=False
        ),
        sa.UniqueConstraint("connector_version_id", "tool_version_id"),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("connection_config", sa.JSON, nullable=False),
        sa.Column("secret_id", sa.String(26), sa.ForeignKey("secrets.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_data_sources_workspace_id_updated_at", "workspace_id", "updated_at"),
    )
    op.create_table(
        "plugins",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_plugins_workspace_id_updated_at", "workspace_id", "updated_at"),
    )
    op.create_table(
        "plugin_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("plugin_id", sa.String(26), sa.ForeignKey("plugins.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("based_on_version_id", sa.String(26)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("plugin_id", "version_number"),
    )
    op.create_table(
        "plugin_version_skill_bindings",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "plugin_version_id", sa.String(26), sa.ForeignKey("plugin_versions.id"), nullable=False
        ),
        sa.Column(
            "skill_version_id", sa.String(26), sa.ForeignKey("skill_versions.id"), nullable=False
        ),
        sa.UniqueConstraint("plugin_version_id", "skill_version_id"),
    )
    op.create_table(
        "plugin_version_tool_bindings",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "plugin_version_id", sa.String(26), sa.ForeignKey("plugin_versions.id"), nullable=False
        ),
        sa.Column(
            "tool_version_id", sa.String(26), sa.ForeignKey("tool_versions.id"), nullable=False
        ),
        sa.UniqueConstraint("plugin_version_id", "tool_version_id"),
    )
    op.create_table(
        "plugin_version_resource_bindings",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "plugin_version_id", sa.String(26), sa.ForeignKey("plugin_versions.id"), nullable=False
        ),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(26), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(768), unique=True),
        sa.Column("external_url", sa.String(2000)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("metadata_json", sa.JSON, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("parent_artifact_id", sa.String(26)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_artifacts_workspace_id_created_at", "workspace_id", "created_at"),
    )
    op.create_table(
        "test_runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_version_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_json", sa.JSON, nullable=False),
        sa.Column("output_json", sa.JSON, nullable=False),
        sa.Column("error_summary", sa.Text),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_test_runs_workspace_id_created_at", "workspace_id", "created_at"),
    )


def downgrade() -> None:
    for table in [
        "test_runs",
        "artifacts",
        "plugin_version_resource_bindings",
        "plugin_version_tool_bindings",
        "plugin_version_skill_bindings",
        "plugin_versions",
        "plugins",
        "data_sources",
        "connector_tool_bindings",
        "tool_versions",
        "tools",
        "connector_versions",
        "connectors",
        "skill_versions",
        "skills",
        "secrets",
        "knowledge_chunks",
        "knowledge_documents",
        "knowledge_bases",
        "files",
        "outbox_events",
        "run_events",
        "runs",
        "messages",
        "conversations",
        "sessions",
        "workspace_members",
        "organization_members",
        "local_credentials",
        "auth_identities",
        "users",
        "workspaces",
        "organizations",
    ]:
        op.drop_table(table)
