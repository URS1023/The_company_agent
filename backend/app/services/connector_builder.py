from __future__ import annotations

import re


def build_connector_spec(
    *,
    name: str,
    description: str,
    provider: str = "http",
    base_url: str = "",
    path: str = "",
    method: str = "POST",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
) -> dict:
    """Turn a human API note into a reviewable, non-secret ToolSpec draft."""

    operation = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_") or "tool"
    return {
        "provider": provider,
        "name": operation,
        "description": description.strip(),
        "base_url": base_url.strip(),
        "path": path.strip(),
        "method": method.upper(),
        "input_schema": input_schema or {"type": "object", "additionalProperties": False},
        "output_schema": output_schema or {"type": "object"},
        "status": "draft",
        "secret_id": None,
    }


__all__ = ["build_connector_spec"]
