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
from backend.app.models.runtime import Message, OutboxEvent, Run
from backend.app.providers.compatible import ProviderConfigurationError, agnes_client
from backend.app.services.runtime import append_run_event, next_message_sequence, update_run_status

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
            chunks: list[str] = []
            async for text in client.stream_chat(
                model=settings.agnes_model,
                messages=[{"role": "user", "content": user_message.content}],
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
