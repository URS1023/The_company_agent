from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from redis.asyncio import Redis

from backend.app.core.config import settings


def redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def elasticsearch_client() -> AsyncElasticsearch:
    kwargs: dict[str, object] = {"hosts": [settings.elasticsearch_url], "request_timeout": 5}
    if settings.elasticsearch_username and settings.elasticsearch_password:
        kwargs["basic_auth"] = (settings.elasticsearch_username, settings.elasticsearch_password)
    return AsyncElasticsearch(**kwargs)


@asynccontextmanager
async def managed_redis() -> AsyncIterator[Redis]:
    client = redis_client()
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def managed_elasticsearch() -> AsyncIterator[AsyncElasticsearch]:
    client = elasticsearch_client()
    try:
        yield client
    finally:
        await client.close()


async def redis_ping() -> tuple[bool, str]:
    try:
        async with managed_redis() as client:
            result = await client.ping()
        return bool(result), "ok" if result else "unexpected_response"
    except Exception as exc:  # pragma: no cover - environment-specific
        return False, type(exc).__name__


async def elasticsearch_ping() -> tuple[bool, str]:
    try:
        async with managed_elasticsearch() as client:
            info = await client.info()
        version = info.get("version", {}).get("number", "unknown")
        return True, str(version)
    except Exception as exc:  # pragma: no cover - environment-specific
        return False, type(exc).__name__


__all__ = [
    "elasticsearch_client",
    "elasticsearch_ping",
    "managed_elasticsearch",
    "managed_redis",
    "redis_client",
    "redis_ping",
]
