from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.core.config import settings


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderResponseError(RuntimeError):
    pass


@dataclass(slots=True)
class ChatResponse:
    text: str
    raw: dict[str, Any]
    tool_calls: list[dict[str, Any]]


class OpenAICompatibleClient:
    """Small adapter for providers exposing the OpenAI Chat/Embedding shapes."""

    def __init__(self, base_url: str, api_key: str | None, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderConfigurationError("provider API key is not configured")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        enable_thinking: bool | None = None,
        stream: bool = False,
    ) -> ChatResponse:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format
        if enable_thinking is not None:
            payload["enable_thinking"] = enable_thinking
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )
        if response.is_error:
            raise ProviderResponseError(f"chat provider returned HTTP {response.status_code}")
        if stream:
            raise ProviderResponseError("use stream_chat for streaming responses")
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        return ChatResponse(text=content, raw=data, tool_calls=message.get("tool_calls", []))

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        enable_thinking: bool | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if enable_thinking is not None:
            payload["enable_thinking"] = enable_thinking
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            ) as response:
                if response.is_error:
                    raise ProviderResponseError(
                        f"chat provider returned HTTP {response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload_text = line[5:].strip()
                    if payload_text == "[DONE]":
                        return
                    try:
                        chunk = json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text

    async def embeddings(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise ProviderConfigurationError("provider API key is not configured")
        payload = {"model": model, "input": inputs, "encoding_format": "float"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json=payload,
            )
        if response.is_error:
            raise ProviderResponseError(f"embedding provider returned HTTP {response.status_code}")
        data = response.json()
        return [
            item["embedding"]
            for item in sorted(data.get("data", []), key=lambda item: item["index"])
        ]


def agnes_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(settings.agnes_base_url, settings.agnes_api_key)


def siliconflow_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(settings.siliconflow_base_url, settings.siliconflow_api_key)


__all__ = [
    "ChatResponse",
    "OpenAICompatibleClient",
    "ProviderConfigurationError",
    "ProviderResponseError",
    "agnes_client",
    "siliconflow_client",
]
