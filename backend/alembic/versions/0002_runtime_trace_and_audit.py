"""Add structured message parts, runtime trace, citations and audit records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_runtime_trace"
down_revision: str | None = "0001_native_gate0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run_events",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint(
        "uq_run_events_run_id_sequence", "run_events", ["run_id", "sequence"]
    )
    op.add_column(
        "data_sources",
        sa.Column("visibility", sa.String(32), nullable=False, server_default="workspace"),
    )
    op.add_column("messages", sa.Column("parts_json", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("parent_run_id", sa.String(26), nullable=True))
    op.add_column("runs", sa.Column("context_snapshot", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("model_profile", sa.String(100), nullable=True))
    op.add_column("runs", sa.Column("cost", sa.Float(), nullable=True))
    op.create_foreign_key("fk_runs_parent_run_id", "runs", "runs", ["parent_run_id"], ["id"])

    op.create_table(
        "run_resource_snapshots",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(26), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_run_resource_snapshots_run_id", "run_id"),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "sequence"),
        sa.Index("ix_run_steps_run_id_sequence", "run_id", "sequence"),
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("step_id", sa.String(26), sa.ForeignKey("run_steps.id"), nullable=True),
        sa.Column(
            "tool_version_id", sa.String(26), sa.ForeignKey("tool_versions.id"), nullable=True
        ),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_tool_calls_run_id_started_at", "run_id", "started_at"),
    )
    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("step_id", sa.String(26), sa.ForeignKey("run_steps.id"), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index("ix_model_calls_run_id_started_at", "run_id", "started_at"),
    )
    op.create_table(
        "citations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("message_id", sa.String(26), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("chunk_id", sa.String(26), sa.ForeignKey("knowledge_chunks.id"), nullable=True),
        sa.Column("file_id", sa.String(26), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_citations_run_id", "run_id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workspace_id", sa.String(26), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(26), nullable=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_audit_logs_workspace_id_created_at", "workspace_id", "created_at"),
    )


def downgrade() -> None:
    for table in [
        "audit_logs",
        "citations",
        "model_calls",
        "tool_calls",
        "run_steps",
        "run_resource_snapshots",
    ]:
        op.drop_table(table)
    op.drop_column("data_sources", "visibility")
    op.drop_constraint("fk_runs_parent_run_id", "runs", type_="foreignkey")
    op.drop_column("runs", "cost")
    op.drop_column("runs", "model_profile")
    op.drop_column("runs", "context_snapshot")
    op.drop_column("runs", "parent_run_id")
    op.drop_column("messages", "parts_json")
    op.drop_constraint("uq_run_events_run_id_sequence", "run_events", type_="unique")
    op.drop_column("run_events", "sequence")
