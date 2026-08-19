from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Message, OutboxEvent, Run, RunEvent


async def append_run_event(
    db: AsyncSession,
    *,
    workspace_id: str,
    run_id: str,
    event_type: str,
    payload: dict,
) -> RunEvent:
    event = RunEvent(
        workspace_id=workspace_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        created_at=utc_now(),
    )
    db.add(event)
    await db.flush()
    return event


async def append_outbox_event(db: AsyncSession, *, topic: str, payload: dict) -> OutboxEvent:
    event = OutboxEvent(
        id=new_id(),
        topic=topic,
        payload=payload,
        created_at=utc_now(),
    )
    db.add(event)
    await db.flush()
    return event


async def next_message_sequence(db: AsyncSession, conversation_id: str) -> int:
    from sqlalchemy import func, select

    current = await db.scalar(
        select(func.max(Message.sequence)).where(Message.conversation_id == conversation_id)
    )
    return int(current or 0) + 1


async def update_run_status(
    db: AsyncSession,
    run: Run,
    *,
    status: str,
    event_type: str,
    payload: dict | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> RunEvent:
    now = utc_now()
    run.status = status
    if status == "running" and run.started_at is None:
        run.started_at = now
    if status in {"completed", "failed", "cancelled"}:
        run.completed_at = now
    run.error_code = error_code
    run.error_summary = error_summary
    return await append_run_event(
        db,
        workspace_id=run.workspace_id,
        run_id=run.id,
        event_type=event_type,
        payload=payload or {},
    )


__all__ = ["append_outbox_event", "append_run_event", "next_message_sequence", "update_run_status"]
