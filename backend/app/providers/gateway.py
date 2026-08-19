from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from backend.app.core.config import settings
from backend.app.providers.compatible import ChatResponse, agnes_client, siliconflow_client


class ModelGateway:
    """Profile-based model router; business code never selects provider URLs."""

    def _client(self, profile: str):
        if profile == "reasoning":
            return agnes_client(), settings.agnes_model
        if profile == "vision":
            return siliconflow_client(), settings.siliconflow_vision_model
        raise ValueError(f"unknown model profile: {profile}")

    async def chat(
        self,
        *,
        profile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        enable_thinking: bool | None = None,
    ) -> ChatResponse:
        client, model = self._client(profile)
        if profile == "vision" and not settings.allow_external_vision:
            raise RuntimeError("VISION_PROFILE_DISABLED")
        if profile == "reasoning" and not settings.allow_external_chat:
            raise RuntimeError("CHAT_PROFILE_DISABLED")
        return await client.chat(
            model=model,
            messages=messages,
            tools=tools,
            enable_thinking=enable_thinking,
        )

    async def stream_chat(
        self,
        *,
        profile: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        client, model = self._client(profile)
        if profile == "reasoning" and not settings.allow_external_chat:
            raise RuntimeError("CHAT_PROFILE_DISABLED")
        async for text in client.stream_chat(model=model, messages=messages, tools=tools):
            yield text

    async def embeddings(self, *, inputs: list[str]) -> list[list[float]]:
        if not settings.allow_external_embedding:
            raise RuntimeError("EMBEDDING_PROFILE_DISABLED")
        return await siliconflow_client().embeddings(
            model=settings.siliconflow_embedding_model, inputs=inputs
        )


__all__ = ["ModelGateway"]
