from __future__ import annotations

import json

import httpx
import pytest

from backend.app.providers.compatible import (
    OpenAICompatibleClient,
    ProviderConfigurationError,
    ProviderResponseError,
)


@pytest.mark.asyncio
async def test_openai_compatible_chat_accepts_tools_and_multimodal_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["model"] == "vision-model"
        assert body["messages"][0]["content"][1]["type"] == "image_url"
        assert body["tools"][0]["function"]["name"] == "echo"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ready",
                            "tool_calls": [
                                {"id": "call-1", "function": {"name": "echo", "arguments": "{}"}}
                            ],
                        }
                    }
                ],
                "usage": {"total_tokens": 3},
            },
        )

    client = OpenAICompatibleClient(
        "https://provider.test/v1",
        "test-key",
        transport=httpx.MockTransport(handler),
    )
    response = await client.chat(
        model="vision-model",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
                ],
            }
        ],
        tools=[{"type": "function", "function": {"name": "echo", "parameters": {}}}],
        enable_thinking=False,
    )
    assert response.text == "ready"
    assert response.tool_calls[0]["id"] == "call-1"


@pytest.mark.asyncio
async def test_openai_compatible_stream_and_embeddings_are_parsed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"choices":[{"delta":{"content":"A"}}]}\n\ndata: [DONE]\n\n',
        )

    client = OpenAICompatibleClient(
        "https://provider.test/v1", "test-key", transport=httpx.MockTransport(handler)
    )
    chunks = [chunk async for chunk in client.stream_chat(model="chat", messages=[])]
    assert chunks == ["A"]
    assert await client.embeddings(model="embed", inputs=["x"]) == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_openai_compatible_provider_errors_are_explicit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    missing_key = OpenAICompatibleClient("https://provider.test/v1", None)
    with pytest.raises(ProviderConfigurationError):
        await missing_key.chat(model="chat", messages=[])
    client = OpenAICompatibleClient(
        "https://provider.test/v1", "bad-key", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderResponseError):
        await client.chat(model="chat", messages=[])


@pytest.mark.asyncio
async def test_openai_compatible_retries_transient_provider_status() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatibleClient(
        "https://provider.test/v1",
        "test-key",
        transport=httpx.MockTransport(handler),
        max_retries=1,
    )
    response = await client.chat(model="chat", messages=[])
    assert response.text == "ok"
    assert calls == 2
