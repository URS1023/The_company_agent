from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

from backend.app.core.config import settings
from backend.app.providers.compatible import (
    ProviderConfigurationError,
    ProviderResponseError,
    agnes_client,
    siliconflow_client,
)

# Keep the smoke probe independent of third-party image hosting. SiliconFlow
# accepts data URLs, while some public hosts reject the provider's downloader
# or return a redirect that is not considered a downloadable image URL.
PUBLIC_TEST_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def run_probe(provider: str) -> dict[str, object]:
    if provider == "agnes":
        client = agnes_client()
        response = await client.chat(
            model=settings.agnes_model,
            messages=[{"role": "user", "content": "Return the word READY."}],
        )
        return {"provider": "agnes", "model": settings.agnes_model, "text": response.text[:100]}
    if provider == "siliconflow-vision":
        client = siliconflow_client()
        response = await client.chat(
            model=settings.siliconflow_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "用一句中文描述图片。"},
                        {"type": "image_url", "image_url": {"url": PUBLIC_TEST_IMAGE}},
                    ],
                }
            ],
        )
        return {
            "provider": "siliconflow",
            "profile": "vision",
            "model": settings.siliconflow_vision_model,
            "text": response.text[:200],
        }
    if provider == "siliconflow-embedding":
        client = siliconflow_client()
        vectors = await client.embeddings(
            model=settings.siliconflow_embedding_model,
            inputs=["企业经营分析测试文本", "招投标文件测试文本"],
        )
        dimensions = sorted({len(vector) for vector in vectors})
        return {
            "provider": "siliconflow",
            "profile": "embedding",
            "model": settings.siliconflow_embedding_model,
            "count": len(vectors),
            "dimensions": dimensions,
        }
    raise ValueError(f"unknown provider: {provider}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live provider capability probe.")
    parser.add_argument(
        "provider",
        choices=["agnes", "siliconflow-vision", "siliconflow-embedding"],
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform an authenticated request instead of a config-only check.",
    )
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({"provider": args.provider, "live": False, "status": "not_called"}))
        return 0
    try:
        result = asyncio.run(run_probe(args.provider))
    except (ProviderConfigurationError, ProviderResponseError, httpx.HTTPError) as exc:
        print(
            json.dumps({"provider": args.provider, "status": "failed", "error": type(exc).__name__})
        )
        return 2
    except Exception as exc:  # pragma: no cover - provider/network-specific
        print(
            json.dumps({"provider": args.provider, "status": "failed", "error": type(exc).__name__})
        )
        return 2
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
