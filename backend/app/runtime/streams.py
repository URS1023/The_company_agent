from __future__ import annotations

from typing import Any

from backend.app.core.config import settings
from backend.app.core.external_services import redis_client


class StreamQueue:
    """Redis Streams queue used by native workers and future container workers."""

    def __init__(self, stream: str | None = None) -> None:
        self.stream = stream or settings.redis_stream_name

    async def publish(self, payload: dict[str, Any]) -> str:
        client = redis_client()
        try:
            values = {key: str(value) for key, value in payload.items()}
            return await client.xadd(self.stream, values)
        finally:
            await client.aclose()

    async def ensure_group(self, group: str | None = None) -> None:
        client = redis_client()
        try:
            try:
                await client.xgroup_create(
                    name=self.stream,
                    groupname=group or settings.redis_consumer_group,
                    id="0",
                    mkstream=True,
                )
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
        finally:
            await client.aclose()


__all__ = ["StreamQueue"]
