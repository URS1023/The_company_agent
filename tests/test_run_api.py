from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.models.runtime import OutboxEvent, Run, RunEvent


def test_conversation_and_run_create_persists_event_and_outbox(
    client, db_session, admin_seed
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert login.status_code == 200
    conversation = client.post("/api/v1/conversations", json={"title": "Gate 0"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]
    run_response = client.post(
        f"/api/v1/runs/conversations/{conversation_id}",
        headers={"Idempotency-Key": "gate-0-run"},
        json={"content": "测试一次 Run", "idempotency_key": "gate-0-run"},
    )
    assert run_response.status_code == 202
    run_id = run_response.json()["id"]

    async def read_records():
        run = await db_session.get(Run, run_id)
        events = list(await db_session.scalars(select(RunEvent).where(RunEvent.run_id == run_id)))
        outbox = list(
            await db_session.scalars(select(OutboxEvent).where(OutboxEvent.topic == "run.created"))
        )
        return run, events, outbox

    run, events, outbox = asyncio.get_event_loop().run_until_complete(read_records())
    assert run is not None
    assert run.status == "queued"
    assert any(event.event_type == "run.created" for event in events)
    assert any(item.payload["run_id"] == run_id for item in outbox)

    async def finish_for_stream_test():
        persisted_run = await db_session.get(Run, run_id)
        persisted_run.status = "completed"
        await db_session.commit()

    asyncio.get_event_loop().run_until_complete(finish_for_stream_test())
    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as events_response:
        assert events_response.status_code == 200
        first_chunk = next(events_response.iter_text())
        assert "run.created" in first_chunk

    proposal = client.post(f"/api/v1/runs/{run_id}/capability-proposals")
    assert proposal.status_code == 200
    assert proposal.json()["capability_type"] == "skill"
    draft = client.post(
        f"/api/v1/runs/{run_id}/capability-drafts", json={"capability_type": "skill"}
    )
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"


def test_run_trace_cancel_retry_and_conversation_lifecycle(client, db_session, admin_seed) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert login.status_code == 200
    conversation = client.post("/api/v1/conversations", json={"title": "可追踪"})
    conversation_id = conversation.json()["id"]
    renamed = client.patch(f"/api/v1/conversations/{conversation_id}", json={"title": "已重命名"})
    assert renamed.status_code == 200
    run_response = client.post(
        f"/api/v1/runs/conversations/{conversation_id}",
        json={"content": "检查步骤"},
    )
    run_id = run_response.json()["id"]
    assert client.get(f"/api/v1/conversations/{conversation_id}/messages").status_code == 200
    assert client.get(f"/api/v1/runs/{run_id}/steps").json() == []
    assert client.get(f"/api/v1/runs/{run_id}/tool-calls").json() == []
    cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    retried = client.post(f"/api/v1/runs/{run_id}/retry")
    assert retried.status_code == 202
    assert retried.json()["parent_run_id"] == run_id
    archived = client.delete(f"/api/v1/conversations/{conversation_id}")
    assert archived.status_code == 204
