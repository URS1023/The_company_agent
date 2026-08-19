from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.models.runtime import Message, ModelCall, Run, RunEvent
from backend.runtime.worker import execute_run


class FakeGateway:
    async def stream_chat(self, **kwargs):
        yield "执行"
        yield "完成"


class NeverGateway:
    def __init__(self):
        raise AssertionError("gateway must not be constructed when Chat is disabled")


@pytest.mark.asyncio
async def test_worker_completes_a_plain_chat_run_and_persists_trace(
    client, db_session, admin_seed, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "allow_external_chat", True)
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
        ).status_code
        == 200
    )
    conversation = client.post("/api/v1/conversations", json={"title": "worker"}).json()
    run = client.post(
        f"/api/v1/runs/conversations/{conversation['id']}",
        json={"content": "执行一条本地 Worker 测试"},
    ).json()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await execute_run(
        run["id"],
        session_factory=session_factory,
        model_gateway_factory=FakeGateway,
    )

    persisted_run = await db_session.get(Run, run["id"])
    assistant = await db_session.scalar(
        select(Message).where(
            Message.conversation_id == conversation["id"], Message.role == "assistant"
        )
    )
    model_call = await db_session.scalar(select(ModelCall).where(ModelCall.run_id == run["id"]))
    events = list(await db_session.scalars(select(RunEvent).where(RunEvent.run_id == run["id"])))
    assert persisted_run is not None and persisted_run.status == "completed"
    assert assistant is not None and assistant.content == "执行完成"
    assert model_call is not None and model_call.status == "completed"
    assert persisted_run.model_usage == {"calls": 1}
    event_types = [event.event_type for event in events]
    assert "run.started" in event_types
    assert "message.delta" in event_types
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_fails_closed_when_external_chat_is_disabled(
    client, db_session, admin_seed, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "allow_external_chat", False)
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}
        ).status_code
        == 200
    )
    conversation = client.post("/api/v1/conversations", json={"title": "disabled"}).json()
    run = client.post(
        f"/api/v1/runs/conversations/{conversation['id']}", json={"content": "should fail closed"}
    ).json()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await execute_run(
        run["id"], session_factory=session_factory, model_gateway_factory=NeverGateway
    )
    persisted_run = await db_session.get(Run, run["id"])
    assert persisted_run is not None
    assert persisted_run.status == "failed"
    assert persisted_run.error_code == "EXTERNAL_CHAT_DISABLED"
