from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Message, OutboxEvent, Run, RunEvent, RunStep


async def append_run_event(
    db: AsyncSession,
    *,
    workspace_id: str,
    run_id: str,
    event_type: str,
    payload: dict,
) -> RunEvent:
    from sqlalchemy import func, select

    current_sequence = await db.scalar(
        select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
    )
    event = RunEvent(
        workspace_id=workspace_id,
        run_id=run_id,
        sequence=int(current_sequence or 0) + 1,
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


async def next_step_sequence(db: AsyncSession, run_id: str) -> int:
    from sqlalchemy import func, select

    current = await db.scalar(select(func.max(RunStep.sequence)).where(RunStep.run_id == run_id))
    return int(current or 0) + 1


async def create_run_step(
    db: AsyncSession,
    *,
    run: Run,
    step_type: str,
    name: str,
    input_json: dict | None = None,
    metadata: dict | None = None,
) -> RunStep:
    step = RunStep(
        id=new_id(),
        workspace_id=run.workspace_id,
        run_id=run.id,
        sequence=await next_step_sequence(db, run.id),
        step_type=step_type,
        name=name,
        status="running",
        input_json=input_json,
        metadata_json=metadata or {},
        started_at=utc_now(),
    )
    db.add(step)
    await db.flush()
    await append_run_event(
        db,
        workspace_id=run.workspace_id,
        run_id=run.id,
        event_type="step.started",
        payload={"step_id": step.id, "sequence": step.sequence, "type": step_type, "name": name},
    )
    return step


async def complete_run_step(
    db: AsyncSession,
    *,
    step: RunStep,
    status: str,
    output_json: dict | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> RunStep:
    step.status = status
    step.output_json = output_json
    step.error_code = error_code
    step.error_summary = error_summary
    step.completed_at = utc_now()
    await append_run_event(
        db,
        workspace_id=step.workspace_id,
        run_id=step.run_id,
        event_type="step.completed" if status == "completed" else "step.failed",
        payload={
            "step_id": step.id,
            "sequence": step.sequence,
            "status": status,
            "error_code": error_code,
        },
    )
    return step


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
    event_payload = dict(payload or {})
    if error_code:
        event_payload.update({"error_code": error_code, "error_summary": error_summary})
    return await append_run_event(
        db,
        workspace_id=run.workspace_id,
        run_id=run.id,
        event_type=event_type,
        payload=event_payload,
    )


__all__ = [
    "append_outbox_event",
    "append_run_event",
    "complete_run_step",
    "create_run_step",
    "next_message_sequence",
    "next_step_sequence",
    "update_run_status",
]
