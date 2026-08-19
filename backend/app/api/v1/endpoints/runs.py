from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.runtime import Conversation, Message, Run, RunEvent
from backend.app.schemas.capabilities import CapabilityProposalResponse
from backend.app.schemas.chat import CreateRunRequest, RunResponse
from backend.app.services.auth import current_user_context
from backend.app.services.capability_builder import propose_from_user_intent
from backend.app.services.runtime import (
    append_outbox_event,
    append_run_event,
    next_message_sequence,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_response(run: Run) -> RunResponse:
    return RunResponse.model_validate(run, from_attributes=True)


async def _owned_run(run_id: str, request: Request, db: AsyncSession) -> tuple[Run, str]:
    user, _, _, membership = await current_user_context(request, db)
    run = await db.scalar(
        select(Run).where(
            Run.id == run_id,
            Run.workspace_id == membership.workspace_id,
            Run.started_by_user_id == user.id,
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run 不存在")
    return run, membership.workspace_id


@router.post(
    "/conversations/{conversation_id}",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    conversation_id: str,
    payload: CreateRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    user, _, _, membership = await current_user_context(request, db)
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == membership.workspace_id,
            Conversation.owner_user_id == user.id,
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    if payload.idempotency_key:
        existing = await db.scalar(
            select(Run).where(
                Run.workspace_id == membership.workspace_id,
                Run.started_by_user_id == user.id,
                Run.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return _run_response(existing)
    now = utc_now()
    run = Run(
        id=new_id(),
        workspace_id=membership.workspace_id,
        conversation_id=conversation.id,
        started_by_user_id=user.id,
        status="queued",
        idempotency_key=payload.idempotency_key,
        created_at=now,
    )
    db.add(run)
    db.add(
        Message(
            id=new_id(),
            workspace_id=membership.workspace_id,
            conversation_id=conversation.id,
            role="user",
            sequence=await next_message_sequence(db, conversation.id),
            content=payload.content,
            status="completed",
            created_at=now,
        )
    )
    conversation.updated_at = now
    await db.flush()
    await append_run_event(
        db,
        workspace_id=membership.workspace_id,
        run_id=run.id,
        event_type="run.created",
        payload={"status": "queued"},
    )
    await append_outbox_event(
        db,
        topic="run.created",
        payload={"run_id": run.id, "workspace_id": membership.workspace_id},
    )
    await db.commit()
    return _run_response(run)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> RunResponse:
    run, _ = await _owned_run(run_id, request, db)
    return _run_response(run)


@router.post("/{run_id}/capability-proposals", response_model=CapabilityProposalResponse)
async def capability_proposal(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CapabilityProposalResponse:
    run, _ = await _owned_run(run_id, request, db)
    message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == run.conversation_id, Message.role == "user")
        .order_by(Message.sequence.desc())
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有找到用户任务")
    proposal = propose_from_user_intent(message.content)
    return CapabilityProposalResponse(
        capability_type=proposal.capability_type,
        name=proposal.name,
        reason=proposal.reason,
        spec=proposal.spec,
    )


@router.get("/{run_id}/events")
async def run_events(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    run, workspace_id = await _owned_run(run_id, request, db)
    last_event_id = request.headers.get("last-event-id") or request.query_params.get("after")
    cursor = int(last_event_id or 0)

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        started = time.monotonic()
        while time.monotonic() - started < 900:
            rows = await db.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run.id,
                    RunEvent.workspace_id == workspace_id,
                    RunEvent.id > cursor,
                )
                .order_by(RunEvent.id)
            )
            emitted = False
            for event in rows:
                cursor = event.id
                emitted = True
                body = {
                    "id": event.id,
                    "event": event.event_type,
                    "run_id": event.run_id,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                serialized = json.dumps(body, ensure_ascii=False)
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {serialized}\n\n"
            if not emitted:
                yield ": heartbeat\n\n"
            current = await db.get(Run, run.id)
            if current and current.status in {"completed", "failed", "cancelled"} and not emitted:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
