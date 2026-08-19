from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    Connector,
    ConnectorVersion,
    Plugin,
    PluginToolBinding,
    PluginVersion,
    Tool,
    ToolVersion,
)
from backend.app.models.runtime import Conversation, Message, Run, RunStep, ToolCall
from backend.app.providers.compatible import ChatResponse
from backend.runtime.worker import execute_run


class ToolLoopGateway:
    calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(
                text="",
                raw={},
                tool_calls=[
                    {
                        "id": "call-finance",
                        "function": {
                            "name": "finance.analyze",
                            "arguments": json.dumps(
                                {"rows": [{"revenue": 10, "cost": 4}], "budget": 5}
                            ),
                        },
                    }
                ],
            )
        return ChatResponse(text="工具结果已整理", raw={}, tool_calls=[])


@pytest.mark.asyncio
async def test_worker_tool_loop_persists_step_and_tool_call(
    db_session, admin_seed, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "allow_external_chat", True)
    now = utc_now()
    workspace_id = admin_seed["workspace_id"]
    user_id = admin_seed["user_id"]
    conversation = Conversation(
        id=new_id(),
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="tool loop",
        created_at=now,
        updated_at=now,
    )
    connector = Connector(
        id=new_id(),
        workspace_id=workspace_id,
        owner_user_id=user_id,
        name="Builtins",
        provider="builtin",
        visibility="private",
        status="active",
        created_at=now,
        updated_at=now,
    )
    connector_version = ConnectorVersion(
        id=new_id(),
        connector_id=connector.id,
        version_number=1,
        status="published",
        spec={},
        created_by=user_id,
        created_at=now,
    )
    tool = Tool(
        id=new_id(),
        workspace_id=workspace_id,
        connector_id=connector.id,
        name="finance.analyze",
        description="Finance",
        status="active",
        created_at=now,
        updated_at=now,
    )
    tool_version = ToolVersion(
        id=new_id(),
        tool_id=tool.id,
        connector_version_id=connector_version.id,
        version_number=1,
        status="published",
        created_by=user_id,
        created_at=now,
        spec={
            "provider": "builtin",
            "name": "finance.analyze",
            "operation": "finance.analyze",
            "input_schema": {"type": "object", "required": ["rows"]},
        },
    )
    plugin = Plugin(
        id=new_id(),
        workspace_id=workspace_id,
        owner_user_id=user_id,
        name="Finance Plugin",
        description="tool loop",
        visibility="private",
        status="active",
        created_at=now,
        updated_at=now,
    )
    plugin_version = PluginVersion(
        id=new_id(),
        plugin_id=plugin.id,
        version_number=1,
        status="published",
        spec={},
        created_by=user_id,
        created_at=now,
    )
    plugin.published_version_id = plugin_version.id
    run = Run(
        id=new_id(),
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        started_by_user_id=user_id,
        plugin_version_id=plugin_version.id,
        status="queued",
        context_snapshot={"runtime_schema_version": 1},
        created_at=now,
    )
    db_session.add_all(
        [
            conversation,
            connector,
            connector_version,
            tool,
            tool_version,
            plugin,
            plugin_version,
            run,
        ]
    )
    await db_session.flush()
    db_session.add(
        PluginToolBinding(
            id=new_id(), plugin_version_id=plugin_version.id, tool_version_id=tool_version.id
        )
    )
    db_session.add(
        Message(
            id=new_id(),
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            role="user",
            sequence=1,
            content="分析财务",
            parts_json=[{"type": "text", "text": "分析财务"}],
            status="completed",
            created_at=now,
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    await execute_run(
        run.id, session_factory=session_factory, model_gateway_factory=ToolLoopGateway
    )
    calls = list(await db_session.scalars(select(ToolCall).where(ToolCall.run_id == run.id)))
    steps = list(await db_session.scalars(select(RunStep).where(RunStep.run_id == run.id)))
    persisted = await db_session.get(Run, run.id)
    assert persisted is not None and persisted.status == "completed"
    assert len(calls) == 1 and calls[0].status == "completed"
    assert len(steps) == 1 and steps[0].status == "completed"
