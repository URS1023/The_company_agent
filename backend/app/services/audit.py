from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    run_id: str | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """Append an audit record without ever accepting secret values.

    Callers should pass identifiers and non-sensitive metadata only.  The helper
    deliberately has no serialization of request bodies so credentials cannot
    accidentally be copied into an audit trail.
    """

    record = AuditLog(
        id=new_id(),
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        run_id=run_id,
        ip_address=ip_address,
        metadata_json=metadata or {},
        created_at=utc_now(),
    )
    db.add(record)
    await db.flush()
    return record


__all__ = ["record_audit"]
