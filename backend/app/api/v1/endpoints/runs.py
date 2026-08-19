from __future__ import annotations

import asyncio
import hashlib
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
from backend.app.models.capabilities import (
    Artifact,
    Connector,
    ConnectorVersion,
    DataSource,
    Plugin,
    PluginVersion,
    Skill,
    SkillVersion,
)
from backend.app.models.files import FileAsset
from backend.app.models.knowledge import KnowledgeBase
from backend.app.models.runtime import (
    Conversation,
    Message,
    Run,
    RunEvent,
    RunResourceSnapshot,
    RunStep,
    ToolCall,
)
from backend.app.schemas.capabilities import (
    CapabilityDraftRequest,
    CapabilityDraftResponse,
    CapabilityProposalResponse,
)
from backend.app.schemas.chat import (
    ContinueRunRequest,
    CreateRunRequest,
    RunResponse,
    RunStepResponse,
    ToolCallResponse,
)
from backend.app.services.audit import record_audit
from backend.app.services.auth import current_user_context
from backend.app.services.capability_builder import propose_from_user_intent
from backend.app.services.diagnostics import classify_failure
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
    plugin_version = None
    if payload.plugin_version_id:
        plugin_version = await db.get(PluginVersion, payload.plugin_version_id)
        plugin = await db.get(Plugin, plugin_version.plugin_id) if plugin_version else None
        if (
            not plugin_version
            or not plugin
            or plugin.workspace_id != membership.workspace_id
            or plugin_version.status != "published"
            or (plugin.visibility != "workspace" and plugin.owner_user_id != user.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="只能使用当前 Workspace 的 Published Plugin Version",
            )
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
    unique_file_ids = list(dict.fromkeys(payload.file_ids))
    unique_kb_ids = list(dict.fromkeys(payload.knowledge_base_ids))
    unique_source_ids = list(dict.fromkeys(payload.data_source_ids))
    unique_artifact_ids = list(dict.fromkeys(payload.artifact_ids))
    unique_connector_ids = list(dict.fromkeys(payload.connector_version_ids))
    files = (
        list(
            await db.scalars(
                select(FileAsset).where(
                    FileAsset.id.in_(unique_file_ids),
                    FileAsset.workspace_id == membership.workspace_id,
                    FileAsset.deleted_at.is_(None),
                    (FileAsset.owner_user_id == user.id) | (membership.role == "admin"),
                )
            )
        )
        if unique_file_ids
        else []
    )
    knowledge_bases = (
        list(
            await db.scalars(
                select(KnowledgeBase).where(
                    KnowledgeBase.id.in_(unique_kb_ids),
                    KnowledgeBase.workspace_id == membership.workspace_id,
                    KnowledgeBase.status == "active",
                    (KnowledgeBase.owner_user_id == user.id)
                    | (KnowledgeBase.visibility == "workspace")
                    | (membership.role == "admin"),
                )
            )
        )
        if unique_kb_ids
        else []
    )
    data_sources = (
        list(
            await db.scalars(
                select(DataSource).where(
                    DataSource.id.in_(unique_source_ids),
                    DataSource.workspace_id == membership.workspace_id,
                    (DataSource.owner_user_id == user.id)
                    | (DataSource.visibility == "workspace")
                    | (membership.role == "admin"),
                    DataSource.status != "archived",
                )
            )
        )
        if unique_source_ids
        else []
    )
    artifacts = (
        list(
            await db.scalars(
                select(Artifact).where(
                    Artifact.id.in_(unique_artifact_ids),
                    Artifact.workspace_id == membership.workspace_id,
                    (Artifact.owner_user_id == user.id) | (membership.role == "admin"),
                )
            )
        )
        if unique_artifact_ids
        else []
    )
    connector_versions = (
        list(
            await db.scalars(
                select(ConnectorVersion)
                .join(Connector)
                .where(
                    ConnectorVersion.id.in_(unique_connector_ids),
                    Connector.workspace_id == membership.workspace_id,
                    (Connector.owner_user_id == user.id)
                    | (Connector.visibility == "workspace")
                    | (membership.role == "admin"),
                    ConnectorVersion.status == "published",
                )
            )
        )
        if unique_connector_ids
        else []
    )
    if (
        len(files) != len(unique_file_ids)
        or len(knowledge_bases) != len(unique_kb_ids)
        or len(data_sources) != len(unique_source_ids)
        or len(artifacts) != len(unique_artifact_ids)
        or len(connector_versions) != len(unique_connector_ids)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="所选资源不存在、不可用或无权访问",
        )
    now = utc_now()
    context_snapshot = {
        "file_ids": unique_file_ids,
        "knowledge_base_ids": unique_kb_ids,
        "data_source_ids": unique_source_ids,
        "artifact_ids": unique_artifact_ids,
        "connector_version_ids": unique_connector_ids,
        "message_parts": payload.message_parts,
        "runtime_schema_version": 1,
        "file_hashes": {file.id: file.sha256 for file in files},
        "artifact_hashes": {artifact.id: artifact.sha256 for artifact in artifacts},
    }
    effective_config_hash = hashlib.sha256(
        json.dumps(context_snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    run = Run(
        id=new_id(),
        workspace_id=membership.workspace_id,
        conversation_id=conversation.id,
        started_by_user_id=user.id,
        plugin_version_id=plugin_version.id if plugin_version else None,
        context_snapshot=context_snapshot,
        model_profile="reasoning",
        effective_config_hash=effective_config_hash,
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
            parts_json=payload.message_parts or [{"type": "text", "text": payload.content}],
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
    for resource_type, resources in (
        ("file", files),
        ("knowledge_base", knowledge_bases),
        ("data_source", data_sources),
        ("artifact", artifacts),
        ("connector_version", connector_versions),
    ):
        for resource in resources:
            snapshot = {
                "id": resource.id,
                "type": resource_type,
                "name": getattr(resource, "name", resource.id),
                "status": getattr(resource, "status", None),
            }
            if hasattr(resource, "sha256"):
                snapshot["sha256"] = resource.sha256
            db.add(
                RunResourceSnapshot(
                    id=new_id(),
                    workspace_id=membership.workspace_id,
                    run_id=run.id,
                    resource_type=resource_type,
                    resource_id=resource.id,
                    snapshot_json=snapshot,
                    created_at=now,
                )
            )
    await record_audit(
        db,
        workspace_id=membership.workspace_id,
        actor_user_id=user.id,
        action="run.created",
        resource_type="run",
        resource_id=run.id,
        run_id=run.id,
        ip_address=request.client.host if request.client else None,
        metadata={"plugin_version_id": plugin_version.id if plugin_version else None},
    )
    await db.commit()
    return _run_response(run)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> RunResponse:
    run, _ = await _owned_run(run_id, request, db)
    return _run_response(run)


@router.get("/{run_id}/steps", response_model=list[RunStepResponse])
async def list_run_steps(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[RunStepResponse]:
    run, _ = await _owned_run(run_id, request, db)
    rows = await db.scalars(
        select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.sequence)
    )
    return [RunStepResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{run_id}/tool-calls", response_model=list[ToolCallResponse])
async def list_tool_calls(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> list[ToolCallResponse]:
    run, _ = await _owned_run(run_id, request, db)
    rows = await db.scalars(
        select(ToolCall).where(ToolCall.run_id == run.id).order_by(ToolCall.started_at)
    )
    return [ToolCallResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> RunResponse:
    run, workspace_id = await _owned_run(run_id, request, db)
    if run.status in {"completed", "failed", "cancelled"}:
        return _run_response(run)
    user, _, _, _ = await current_user_context(request, db)
    run.status = "cancelled"
    run.completed_at = utc_now()
    await append_run_event(
        db,
        workspace_id=workspace_id,
        run_id=run.id,
        event_type="run.cancelled",
        payload={"requested_by": user.id},
    )
    await record_audit(
        db,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="run.cancelled",
        resource_type="run",
        resource_id=run.id,
        run_id=run.id,
    )
    await db.commit()
    return _run_response(run)


async def _enqueue_derived_run(
    *,
    db: AsyncSession,
    request: Request,
    source: Run,
    user_id: str,
    content: str,
    parent_run_id: str,
    message_parts: list[dict] | None = None,
    idempotency_key: str | None = None,
) -> Run:
    now = utc_now()
    if idempotency_key:
        existing = await db.scalar(
            select(Run).where(
                Run.workspace_id == source.workspace_id,
                Run.started_by_user_id == user_id,
                Run.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing
    derived = Run(
        id=new_id(),
        workspace_id=source.workspace_id,
        conversation_id=source.conversation_id,
        started_by_user_id=user_id,
        plugin_version_id=source.plugin_version_id,
        parent_run_id=parent_run_id,
        status="queued",
        idempotency_key=idempotency_key,
        context_snapshot=dict(source.context_snapshot or {}),
        model_profile=source.model_profile or "reasoning",
        effective_config_hash=source.effective_config_hash,
        created_at=now,
    )
    db.add(derived)
    db.add(
        Message(
            id=new_id(),
            workspace_id=source.workspace_id,
            conversation_id=source.conversation_id,
            role="user",
            sequence=await next_message_sequence(db, source.conversation_id),
            content=content,
            parts_json=message_parts or [{"type": "text", "text": content}],
            status="completed",
            created_at=now,
        )
    )
    await db.flush()
    await append_run_event(
        db,
        workspace_id=source.workspace_id,
        run_id=derived.id,
        event_type="run.created",
        payload={"status": "queued", "parent_run_id": parent_run_id},
    )
    await append_run_event(
        db,
        workspace_id=source.workspace_id,
        run_id=derived.id,
        event_type="run.continuation_created",
        payload={"parent_run_id": parent_run_id},
    )
    await append_outbox_event(
        db,
        topic="run.created",
        payload={"run_id": derived.id, "workspace_id": source.workspace_id},
    )
    await record_audit(
        db,
        workspace_id=source.workspace_id,
        actor_user_id=user_id,
        action="run.derived",
        resource_type="run",
        resource_id=derived.id,
        run_id=derived.id,
        metadata={"parent_run_id": parent_run_id},
    )
    return derived


@router.post("/{run_id}/retry", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_run(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> RunResponse:
    source, _ = await _owned_run(run_id, request, db)
    user, _, _, _ = await current_user_context(request, db)
    if source.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="只有失败或已取消 Run 可以重试"
        )
    message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == source.conversation_id, Message.role == "user")
        .order_by(Message.sequence.desc())
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有找到原始用户消息")
    derived = await _enqueue_derived_run(
        db=db,
        request=request,
        source=source,
        user_id=user.id,
        content=message.content,
        parent_run_id=source.id,
        message_parts=message.parts_json,
    )
    await db.commit()
    return _run_response(derived)


@router.post("/{run_id}/continue", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def continue_run(
    run_id: str,
    payload: ContinueRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    source, _ = await _owned_run(run_id, request, db)
    user, _, _, _ = await current_user_context(request, db)
    if source.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有已完成 Run 可以续接")
    derived = await _enqueue_derived_run(
        db=db,
        request=request,
        source=source,
        user_id=user.id,
        content=payload.content,
        parent_run_id=source.id,
        message_parts=payload.message_parts,
        idempotency_key=payload.idempotency_key,
    )
    await db.commit()
    return _run_response(derived)


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


@router.post("/{run_id}/capability-drafts", response_model=CapabilityDraftResponse)
async def create_capability_draft(
    run_id: str,
    payload: CapabilityDraftRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CapabilityDraftResponse:
    run, workspace_id = await _owned_run(run_id, request, db)
    user, _, _, _ = await current_user_context(request, db)
    message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == run.conversation_id, Message.role == "user")
        .order_by(Message.sequence.desc())
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有找到用户任务")
    proposal = propose_from_user_intent(message.content)
    if proposal.capability_type != payload.capability_type and payload.capability_type == "skill":
        spec = {"instructions": message.content, "rules": [], "required_resources": []}
        name = "可复用工作方法"
    else:
        spec = proposal.spec
        name = proposal.name
    now = utc_now()
    if payload.capability_type == "skill":
        skill = Skill(
            id=new_id(),
            workspace_id=workspace_id,
            owner_user_id=user.id,
            name=name,
            description=proposal.reason,
            visibility="private",
            created_at=now,
            updated_at=now,
        )
        version = SkillVersion(
            id=new_id(),
            skill_id=skill.id,
            version_number=1,
            status="draft",
            spec=spec,
            created_by=user.id,
            created_at=now,
        )
        db.add_all([skill, version])
        resource_id = skill.id
    else:
        plugin = Plugin(
            id=new_id(),
            workspace_id=workspace_id,
            owner_user_id=user.id,
            name=name,
            description=proposal.reason,
            visibility="private",
            created_at=now,
            updated_at=now,
        )
        version = PluginVersion(
            id=new_id(),
            plugin_id=plugin.id,
            version_number=1,
            status="draft",
            spec=spec,
            created_by=user.id,
            created_at=now,
        )
        db.add_all([plugin, version])
        resource_id = plugin.id
    await record_audit(
        db,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        action="capability.draft_created",
        resource_type=payload.capability_type,
        resource_id=resource_id,
        run_id=run.id,
    )
    await db.commit()
    return CapabilityDraftResponse(
        capability_type=payload.capability_type,
        resource_id=resource_id,
        version_id=version.id,
    )


@router.get("/{run_id}/diagnosis")
async def run_diagnosis(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    run, _ = await _owned_run(run_id, request, db)
    if run.status not in {"failed", "cancelled"}:
        return {"status": run.status, "diagnosis": None}
    return {
        "status": run.status,
        "error_code": run.error_code,
        "error_summary": run.error_summary,
        "diagnosis": classify_failure(run.error_code, run.error_summary),
    }


@router.get("/{run_id}/events")
async def run_events(
    run_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    run, workspace_id = await _owned_run(run_id, request, db)
    stream_run_id = run.id
    last_event_id = request.headers.get("last-event-id") or request.query_params.get("after")
    cursor = int(last_event_id or 0)

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        started = time.monotonic()
        try:
            while time.monotonic() - started < 900:
                rows = list(
                    await db.scalars(
                        select(RunEvent)
                        .where(
                            RunEvent.run_id == stream_run_id,
                            RunEvent.workspace_id == workspace_id,
                            RunEvent.id > cursor,
                        )
                        .order_by(RunEvent.id)
                    )
                )
                current = await db.get(Run, stream_run_id)
                event_rows = [
                    {
                        "id": event.id,
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "run_id": event.run_id,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in rows
                ]
                current_status = current.status if current else None
                # SSE polling must not hold an open read transaction between ticks.
                await db.rollback()
                emitted = False
                for event in event_rows:
                    cursor = event["id"]
                    emitted = True
                    body = {
                        "id": event["id"],
                        "sequence": event["sequence"],
                        "schema_version": 1,
                        "event": event["event_type"],
                        "run_id": event["run_id"],
                        "payload": event["payload"],
                        "created_at": event["created_at"],
                    }
                    serialized = json.dumps(body, ensure_ascii=False)
                    yield f"id: {event['id']}\nevent: {event['event_type']}\ndata: {serialized}\n\n"
                if not emitted:
                    yield ": heartbeat\n\n"
                if current_status in {"completed", "failed", "cancelled"} and not emitted:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
