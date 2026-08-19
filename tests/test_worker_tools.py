from __future__ import annotations

import pytest

from backend.app.core.ids import new_id
from backend.app.core.security import utc_now
from backend.app.models.capabilities import Connector, ConnectorVersion, Tool, ToolVersion
from backend.app.models.runtime import Conversation, Run
from backend.runtime.worker import dispatch_tool


@pytest.mark.asyncio
async def test_worker_dispatches_safe_python_tool_without_host_imports(
    db_session, admin_seed
) -> None:
    now = utc_now()
    conversation = Conversation(
        id=new_id(),
        workspace_id=admin_seed["workspace_id"],
        owner_user_id=admin_seed["user_id"],
        title="sandbox",
        created_at=now,
        updated_at=now,
    )
    run = Run(
        id=new_id(),
        workspace_id=admin_seed["workspace_id"],
        conversation_id=conversation.id,
        started_by_user_id=admin_seed["user_id"],
        status="running",
        created_at=now,
    )
    connector = Connector(
        id=new_id(),
        workspace_id=admin_seed["workspace_id"],
        owner_user_id=admin_seed["user_id"],
        name="Trusted Sandbox",
        provider="sandbox",
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
        created_by=admin_seed["user_id"],
        created_at=now,
    )
    tool = Tool(
        id=new_id(),
        workspace_id=admin_seed["workspace_id"],
        connector_id=connector.id,
        name="python.safe",
        description="Safe data transform",
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
        spec={
            "provider": "sandbox",
            "name": "python.safe",
            "operation": "python.safe",
            "input_schema": {
                "type": "object",
                "required": ["code"],
                "properties": {"code": {"type": "string"}, "data": {}},
            },
        },
        created_by=admin_seed["user_id"],
        created_at=now,
    )
    db_session.add_all([conversation, run, connector, connector_version, tool, tool_version])
    await db_session.flush()
    result = await dispatch_tool(
        db_session,
        run,
        tool_version,
        {
            "code": "result = [row['value'] * 2 for row in data]",
            "data": [{"value": 3}],
        },
    )
    assert result == {"status": "success", "data": [6]}
