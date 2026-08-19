from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.external_services import redis_client
from backend.app.core.ids import new_id
from backend.app.core.logging import configure_logging
from backend.app.core.secrets import SecretManager
from backend.app.core.security import utc_now
from backend.app.models.capabilities import (
    Connector,
    ConnectorVersion,
    DataSource,
    PluginToolBinding,
    PluginVersion,
    SecretRecord,
    Tool,
    ToolVersion,
)
from backend.app.models.runtime import Message, ModelCall, OutboxEvent, Run, ToolCall
from backend.app.providers.compatible import ProviderConfigurationError
from backend.app.providers.gateway import ModelGateway
from backend.app.services.connectors import invoke_database_tool, test_http_connector
from backend.app.services.context import persist_citations, resolve_context
from backend.app.services.parameter_compiler import compile_arguments
from backend.app.services.runtime import (
    append_run_event,
    complete_run_step,
    create_run_step,
    next_message_sequence,
    update_run_status,
)
from backend.app.tools.builtin import analyze_bidding, analyze_finance
from backend.app.tools.gateway import validate_source_policy
from backend.app.tools.http import validate_target
from backend.app.tools.mcp import StreamableHttpMcpClient
from backend.app.tools.sandbox import run_trusted_sandbox

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
    bindings: list[PluginToolBinding] = []
    direct_versions: list[ToolVersion] = []
    if run.plugin_version_id:
        plugin_version = await db.get(PluginVersion, run.plugin_version_id)
        if plugin_version and plugin_version.status == "published":
            bindings.extend(
                list(
                    await db.scalars(
                        select(PluginToolBinding).where(
                            PluginToolBinding.plugin_version_id == plugin_version.id
                        )
                    )
                )
            )
    selected_connector_ids = (run.context_snapshot or {}).get("connector_version_ids", [])
    if selected_connector_ids:
        direct_versions.extend(
            list(
                await db.scalars(
                    select(ToolVersion).where(
                        ToolVersion.connector_version_id.in_(selected_connector_ids),
                        ToolVersion.status == "published",
                    )
                )
            )
        )
    definitions: list[dict] = []
    versions: dict[str, ToolVersion] = {}
    seen: set[str] = set()
    tool_versions = list(direct_versions)
    for binding in bindings:
        tool_version = await db.get(ToolVersion, binding.tool_version_id)
        if tool_version:
            tool_versions.append(tool_version)
    for tool_version in tool_versions:
        if not tool_version or tool_version.status not in {"published", "draft"}:
            continue
        tool = await db.get(Tool, tool_version.tool_id)
        if not tool or tool.status != "active":
            continue
        spec = tool_version.spec or {}
        tool_name = str(spec.get("name", tool_version.id))
        if tool_name in seen:
            continue
        seen.add(tool_name)
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": spec.get("description", ""),
                    "parameters": spec.get("input_schema", {"type": "object"}),
                },
            }
        )
        versions[tool_name] = tool_version
    return definitions, versions


async def load_secret(db, secret_id: str | None, workspace_id: str) -> SecretRecord | None:
    if not secret_id:
        return None
    return await db.scalar(
        select(SecretRecord).where(
            SecretRecord.id == secret_id,
            SecretRecord.workspace_id == workspace_id,
            SecretRecord.deleted_at.is_(None),
        )
    )


def secret_headers(secret: SecretRecord | None, spec: dict) -> dict[str, str]:
    headers = {str(key): str(value) for key, value in (spec.get("headers") or {}).items()}
    if not secret:
        return headers
    values = SecretManager().decrypt(secret.nonce, secret.ciphertext)
    auth_type = str(spec.get("auth_type", "bearer")).lower()
    if auth_type == "api_key" and values.get("api_key"):
        headers[str(spec.get("api_key_header", "X-API-Key"))] = values["api_key"]
    elif auth_type == "basic" and values.get("username") and values.get("password"):
        import base64

        token = base64.b64encode(f"{values['username']}:{values['password']}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    elif values.get("token"):
        headers["Authorization"] = f"Bearer {values['token']}"
    return headers


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


async def dispatch_tool(db, run: Run, tool_version: ToolVersion, arguments: dict) -> dict:
    spec = tool_version.spec or {}
    source_metadata = {key: value for key, value in arguments.items() if key.startswith("__")}
    business_arguments = {
        key: value for key, value in arguments.items() if not key.startswith("__")
    }
    arguments = compile_arguments(
        business_arguments,
        spec.get("input_schema") or {"type": "object"},
        defaults=spec.get("defaults") or {},
    )
    validate_source_policy({**arguments, **source_metadata}, spec.get("field_source_policy"))
    connector_version = await db.get(ConnectorVersion, tool_version.connector_version_id)
    connector = (
        await db.get(Connector, connector_version.connector_id) if connector_version else None
    )
    provider = spec.get("provider") or (connector.provider if connector else "builtin")
    if provider == "builtin":
        return await dispatch_builtin(tool_version, arguments)
    if provider == "sandbox":
        return await run_trusted_sandbox(
            str(spec.get("operation", "")),
            arguments,
            workdir=Path(settings.local_storage_root) / "runs" / run.id,
        )
    if provider == "http":
        if not connector_version:
            raise ValueError("connector version not found")
        secret_id = spec.get("secret_id") or (connector_version.spec or {}).get("secret_id")
        secret = await load_secret(db, secret_id, run.workspace_id)
        return await test_http_connector(connector_version, arguments, secret)
    if provider == "database":
        source_id = spec.get("data_source_id") or arguments.get("data_source_id")
        if not source_id:
            selected = (run.context_snapshot or {}).get("data_source_ids", [])
            source_id = selected[0] if selected else None
        source = await db.scalar(
            select(DataSource).where(
                DataSource.id == source_id,
                DataSource.workspace_id == run.workspace_id,
            )
        )
        if not source:
            raise ValueError("database data source not found")
        secret = await db.get(SecretRecord, source.secret_id) if source.secret_id else None
        operation = str(spec.get("operation") or spec.get("name") or "database.query")
        return await invoke_database_tool(source, secret, operation, arguments)
    if provider == "mcp":
        if not connector_version:
            raise ValueError("connector version not found")
        endpoint = str(spec.get("endpoint") or (connector_version.spec or {}).get("endpoint") or "")
        validate_target(endpoint, allow_private=bool(spec.get("allow_private", False)))
        secret_id = spec.get("secret_id") or (connector_version.spec or {}).get("secret_id")
        secret = await load_secret(db, secret_id, run.workspace_id)
        client = StreamableHttpMcpClient(endpoint, headers=secret_headers(secret, spec))
        await client.initialize()
        result = await client.call_tool(str(spec.get("name", tool_version.id)), arguments)
        return {
            "status": "success",
            "data": result,
            "artifacts": [],
            "metadata": {"provider": "mcp"},
        }
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
            client = ModelGateway()
            tool_definitions, tool_versions = await load_tool_context(db, run)
            messages, citations = await resolve_context(
                db, run=run, user_message=user_message.content
            )
            answer = ""
            streamed_answer = False
            model_usage: dict[str, int] = {"calls": 0}
            started_monotonic = time.monotonic()
            if tool_definitions:
                for _ in range(12):
                    if time.monotonic() - started_monotonic > 20 * 60:
                        raise RuntimeError("RUN_TIMEOUT")
                    if (await db.get(Run, run.id)).status == "cancelled":
                        return
                    model_call = ModelCall(
                        id=new_id(),
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        provider="agnes",
                        model=settings.agnes_model,
                        status="running",
                        metadata_json={"tool_count": len(tool_definitions)},
                        started_at=utc_now(),
                    )
                    db.add(model_call)
                    await db.commit()
                    try:
                        response = await client.chat(
                            profile="reasoning",
                            messages=messages,
                            tools=tool_definitions,
                        )
                    except Exception as model_exc:
                        model_call.status = "failed"
                        model_call.error_code = type(model_exc).__name__
                        model_call.completed_at = utc_now()
                        await db.commit()
                        raise
                    model_call.status = "completed"
                    model_call.completed_at = utc_now()
                    usage = response.raw.get("usage") if isinstance(response.raw, dict) else None
                    model_call.usage_json = usage
                    model_usage["calls"] += 1
                    if isinstance(usage, dict):
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            if isinstance(usage.get(key), int):
                                model_usage[key] = model_usage.get(key, 0) + usage[key]
                    await db.commit()
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
                        step = await create_run_step(
                            db,
                            run=run,
                            step_type="tool",
                            name=tool_name,
                            input_json=arguments,
                        )
                        tool_call = ToolCall(
                            id=new_id(),
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            step_id=step.id,
                            tool_version_id=tool_versions.get(tool_name).id
                            if tool_versions.get(tool_name)
                            else None,
                            tool_name=tool_name,
                            arguments_json=arguments,
                            status="running",
                            idempotency_key=f"{run.id}:{step.sequence}:{tool_name}",
                            started_at=utc_now(),
                        )
                        db.add(tool_call)
                        await db.flush()
                        await append_run_event(
                            db,
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            event_type="tool.started",
                            payload={
                                "tool": tool_name,
                                "step_id": step.id,
                                "tool_call_id": tool_call.id,
                            },
                        )
                        tool_version = tool_versions.get(tool_name)
                        try:
                            if not tool_version:
                                raise ValueError("tool is not published")
                            result = await dispatch_tool(db, run, tool_version, arguments)
                        except Exception as tool_exc:
                            tool_call.status = "failed"
                            tool_call.error_code = type(tool_exc).__name__
                            tool_call.error_summary = str(tool_exc)[:1000]
                            tool_call.completed_at = utc_now()
                            await complete_run_step(
                                db,
                                step=step,
                                status="failed",
                                error_code=type(tool_exc).__name__,
                                error_summary=str(tool_exc)[:1000],
                            )
                            await append_run_event(
                                db,
                                workspace_id=run.workspace_id,
                                run_id=run.id,
                                event_type="tool.failed",
                                payload={
                                    "tool": tool_name,
                                    "step_id": step.id,
                                    "error": str(tool_exc)[:1000],
                                },
                            )
                            await db.commit()
                            raise
                        tool_call.status = "completed"
                        tool_call.result_json = result
                        tool_call.completed_at = utc_now()
                        await complete_run_step(
                            db, step=step, status="completed", output_json=result
                        )
                        await append_run_event(
                            db,
                            workspace_id=run.workspace_id,
                            run_id=run.id,
                            event_type="tool.completed",
                            payload={
                                "tool": tool_name,
                                "step_id": step.id,
                                "tool_call_id": tool_call.id,
                                "status": result.get("status", "success"),
                            },
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
                model_call = ModelCall(
                    id=new_id(),
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    provider="agnes",
                    model=settings.agnes_model,
                    status="running",
                    metadata_json={"stream": True},
                    started_at=utc_now(),
                )
                db.add(model_call)
                await db.commit()
                try:
                    async for text in client.stream_chat(
                        profile="reasoning",
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
                except Exception as model_exc:
                    model_call.status = "failed"
                    model_call.error_code = type(model_exc).__name__
                    model_call.completed_at = utc_now()
                    await db.commit()
                    raise
                answer = "".join(chunks)
                model_call.status = "completed"
                model_call.completed_at = utc_now()
                model_usage["calls"] += 1
                await db.commit()
            if answer and not streamed_answer:
                await append_run_event(
                    db,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    event_type="message.delta",
                    payload={"text": answer},
                )
            db.add(
                assistant_message := Message(
                    id=new_id(),
                    workspace_id=run.workspace_id,
                    conversation_id=run.conversation_id,
                    role="assistant",
                    sequence=await next_message_sequence(db, run.conversation_id),
                    content=answer,
                    status="completed",
                    parts_json=[{"type": "text", "text": answer}],
                    created_at=utc_now(),
                )
            )
            await db.flush()
            await persist_citations(
                db,
                run=run,
                message_id=assistant_message.id,
                citations=citations,
            )
            run.model_usage = model_usage
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
        except Exception as exc:
            logger.exception("run execution failed run_id=%s", run.id)
            await update_run_status(
                db,
                run,
                status="failed",
                event_type="run.failed",
                error_code="RUNTIME_ERROR",
                error_summary="执行过程中发生错误：" + type(exc).__name__,
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
