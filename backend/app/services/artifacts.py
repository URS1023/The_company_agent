from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.core.storage import LocalFileStorage
from backend.app.models.capabilities import Artifact
from backend.app.models.runtime import Run
from backend.app.services.audit import record_audit
from backend.app.services.runtime import append_run_event


async def persist_artifact(
    db: AsyncSession,
    *,
    run: Run,
    owner_user_id: str,
    artifact_type: str,
    name: str,
    mime_type: str,
    content: bytes,
    metadata: dict | None = None,
    parent_artifact_id: str | None = None,
) -> Artifact:
    artifact_id = new_id()
    safe_name = name.replace("\\", "_").replace("/", "_")
    storage_key = f"workspaces/{run.workspace_id}/artifacts/{artifact_id}/{safe_name}"
    file_metadata = LocalFileStorage().put_bytes(storage_key, content)
    artifact = Artifact(
        id=artifact_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        owner_user_id=owner_user_id,
        type=artifact_type,
        name=name,
        mime_type=mime_type,
        size=int(file_metadata["size"]),
        storage_key=storage_key,
        sha256=hashlib.sha256(content).hexdigest(),
        metadata_json=metadata or {},
        status="ready",
        parent_artifact_id=parent_artifact_id,
        created_at=utc_now(),
    )
    db.add(artifact)
    await db.flush()
    await append_run_event(
        db,
        workspace_id=run.workspace_id,
        run_id=run.id,
        event_type="artifact.created",
        payload={
            "artifact_id": artifact.id,
            "type": artifact.type,
            "name": artifact.name,
        },
    )
    await record_audit(
        db,
        workspace_id=run.workspace_id,
        actor_user_id=owner_user_id,
        action="artifact.created",
        resource_type="artifact",
        resource_id=artifact.id,
        run_id=run.id,
        metadata={"type": artifact.type, "name": artifact.name},
    )
    return artifact


__all__ = ["persist_artifact"]
