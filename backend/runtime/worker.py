from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.external_services import redis_client
from backend.app.core.ids import new_id
from backend.app.core.logging import configure_logging
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    ConnectorVersion,
    PluginToolBinding,
    PluginVersion,
    ToolVersion,
)
from backend.app.models.runtime import Message, OutboxEvent, Run
from backend.app.providers.compatible import ProviderConfigurationError, agnes_client
from backend.app.services.connectors import test_http_connector
from backend.app.services.runtime import append_run_event, next_message_sequence, update_run_status
from backend.app.tools.builtin import analyze_bidding, analyze_finance

logger = logging.getLogger(__name__)


async def relay_once(limit: int = 50) -> int:
    published = 0
    async with SessionLocal() as db:
        rows = list(
            await db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
            )
        )
        if not rows:
            return 0
        client = redis_client()
        try:
            for row in rows:
                await client.xadd(
                    settings.redis_stream_name,
                    {"topic": row.topic, "payload": json.dumps(row.payload, ensure_ascii=False)},
                )
                row.published_at = utc_now()
                published += 1
            await db.commit()
        finally:
            await client.aclose()
    return published


async def relay_forever() -> None:
    while True:
        try:
            count = await relay_once()
            if not count:
                await asyncio.sleep(0.5)
        except Exception:
            logger.exception("outbox relay failed")
            await asyncio.sleep(2)


async def load_tool_context(db, run: Run) -> tuple[list[dict], dict[str, ToolVersion]]:
    if not run.plugin_version_id:
        return [], {}
    plugin_version = await db.get(PluginVersion, run.plugin_version_id)
    if not plugin_version or plugin_version.status != "published":
        return [], {}
    bindings = list(
        await db.scalars(
            select(PluginToolBinding).where(
                PluginToolBinding.plugin_version_id == plugin_version.id
            )
        )
    )
    definitions: list[dict] = []
    versions: dict[str, ToolVersion] = {}
    for binding in bindings:
        tool_version = await db.get(ToolVersion, binding.tool_version_id)
        if not tool_version or tool_version.status not in {"published", "draft"}:
            continue
        spec = tool_version.spec or {}
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": spec.get("name", tool_version.id),
                    "description": spec.get("description", ""),
                    "parameters": spec.get("input_schema", {"type": "object"}),
                },
            }
        )
        versions[spec.get("name", tool_version.id)] = tool_version
    return definitions, versions


async def dispatch_builtin(tool_version: ToolVersion, arguments: dict) -> dict:
    operation = str((tool_version.spec or {}).get("operation", ""))
    if operation == "finance.analyze":
        return analyze_finance(rows=arguments.get("rows", []), budget=arguments.get("budget", 0))
    if operation == "bidding.analyze":
        result = analyze_bidding(
            project_name=arguments.get("project_name", ""),
            requirements=arguments.get("requirements", []),
            knowledge_text=arguments.get("knowledge_text", ""),
            template_sections=arguments.get("template_sections"),
        )
        return {
            "requirement_spec": result.requirement_spec,
            "missing": result.missing,
            "document_spec": result.document_spec,
        }
    raise ValueError("unknown builtin tool operation")


async def dispatch_tool(db, tool_version: ToolVersion, arguments: dict) -> dict:
    spec = tool_version.spec or {}
    provider = spec.get("provider", "builtin")
    if provider == "builtin":
        return await dispatch_builtin(tool_version, arguments)
    if provider == "http":
        connector_version = await db.get(ConnectorVersion, tool_version.connector_version_id)
        if not connector_version:
            raise ValueError("connector version not found")
        return await test_http_connector(connector_version, arguments)
    raise ValueError(f"native worker does not support provider {provider}")


async def ensure_group(client: Any) -> None:
    try:
        await client.xgroup_create(
            settings.redis_stream_name,
            settings.redis_consumer_group,
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def execute_run(run_id: str) -> None:
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        if not run or run.status not in {"queued", "created"}:
            return
        await update_run_status(db, run, status="running", event_type="run.started")
        await db.commit()
        user_message = await db.scalar(
            select(Message)
            .where(Message.conversation_id == run.conversation_id, Message.role == "user")
            .order_by(Message.sequence.desc())
        )
        if not user_message:
            await update_run_status(
                db,
                run,
                status="failed",
                event_type="run.failed",
                error_code="USER_MESSAGE_NOT_FOUND",
                error_summary="没有找到待处理的用户消息",
            )
            await db.commit()
            return
        if not settings.allow_external_chat:
            await update_run_status(
                db,
                run,
                status="failed",
                event_type="run.failed",
                error_code="EXTERNAL_CHAT_DISABLED",
                error_summary="当前 Workspace 未开启外部 Chat 模型处理",
            )
            await db.commit()
            return
        try:
            client = agnes_client()
            tool_definitions, tool_versions = await load_tool_context(db, run)
            messages: list[dict[str, Any]] = [{"role": "user", "content": user_message.content}]
            answer = ""
            streamed_answer = False
            if tool_definitions:
                for _ in range(8):
                    response = await client.chat(
                        model=settings.agnes_model,
                        messages=messages,
                        tools=tool_definitions,
                    )
                    if not response.tool_calls:
                        answer = response.text
                        break
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.text or "",
                            "tool_calls": response.tool_calls,
                        }
                    )
                    for call in response.tool_calls:
                        function = call.get("function", {})
                        tool_name = function.get("name", "")
                        raw_arguments = function.get("arguments", "{}")
                        arguments = (
                            json.loads(raw_arguments)
                            if isinstance(raw_arguments, str)
                            else raw_arguments
                        )
                        await append_run_event(
                            db,
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            event_type="tool.started",
                            payload={"tool": tool_name},
                        )
                        tool_version = tool_versions.get(tool_name)
                        if not tool_version:
                            result = {"status": "failed", "error": "tool is not published"}
                        else:
                            result = await dispatch_tool(db, tool_version, arguments)
                        await append_run_event(
                            db,
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            event_type="tool.completed",
                            payload={"tool": tool_name, "status": result.get("status", "success")},
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", tool_name),
                                "name": tool_name,
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )
                    await db.commit()
                if not answer:
                    raise RuntimeError("agent tool loop exceeded maximum steps")
            else:
                streamed_answer = True
                chunks: list[str] = []
                async for text in client.stream_chat(
                    model=settings.agnes_model,
                    messages=messages,
                ):
                    chunks.append(text)
                    await append_run_event(
                        db,
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        event_type="message.delta",
                        payload={"text": text},
                    )
                    await db.commit()
                answer = "".join(chunks)
            if answer and not streamed_answer:
                await append_run_event(
                    db,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    event_type="message.delta",
                    payload={"text": answer},
                )
            db.add(
                Message(
                    id=new_id(),
                    workspace_id=run.workspace_id,
                    conversation_id=run.conversation_id,
                    role="assistant",
                    sequence=await next_message_sequence(db, run.conversation_id),
                    content=answer,
                    status="completed",
                    created_at=utc_now(),
                )
            )
            await update_run_status(
                db,
                run,
                status="completed",
                event_type="run.completed",
                payload={"text_length": len(answer)},
            )
            await db.commit()
        except ProviderConfigurationError:
            await update_run_status(
                db,
                run,
                status="failed",
                event_type="run.failed",
                error_code="MODEL_NOT_CONFIGURED",
                error_summary="Agnes API Key 尚未配置",
            )
            await db.commit()
        except Exception:
            logger.exception("run execution failed run_id=%s", run.id)
            await update_run_status(
                db,
                run,
                status="failed",
                event_type="run.failed",
                error_code="RUNTIME_ERROR",
                error_summary="执行过程中发生未分类错误",
            )
            await db.commit()


async def agent_forever() -> None:
    consumer = f"{socket.gethostname()}-{id(asyncio.current_task())}"
    client = redis_client()
    await ensure_group(client)
    try:
        while True:
            messages = await client.xreadgroup(
                groupname=settings.redis_consumer_group,
                consumername=consumer,
                streams={settings.redis_stream_name: ">"},
                count=1,
                block=1000,
            )
            for _, entries in messages:
                for message_id, values in entries:
                    try:
                        payload = json.loads(values.get("payload", "{}"))
                        if values.get("topic") == "run.created" and payload.get("run_id"):
                            await execute_run(payload["run_id"])
                        await client.xack(
                            settings.redis_stream_name,
                            settings.redis_consumer_group,
                            message_id,
                        )
                    except Exception:
                        logger.exception("worker event failed id=%s", message_id)
    finally:
        await client.aclose()


async def run(role: str) -> None:
    if role == "relay":
        await relay_forever()
    elif role == "agent":
        await agent_forever()
    else:
        raise ValueError("role must be relay or agent")


def main() -> None:
    import argparse

    configure_logging()
    parser = argparse.ArgumentParser(description="Run native Company Agent workers")
    parser.add_argument("role", choices=["relay", "agent"])
    args = parser.parse_args()
    asyncio.run(run(args.role))


if __name__ == "__main__":
    main()
