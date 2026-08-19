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
