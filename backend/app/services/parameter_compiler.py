from __future__ import annotations

import json
from typing import Any

from backend.app.tools.gateway import ToolValidationError, validate_arguments


def compile_arguments(
    raw_arguments: dict[str, Any] | str,
    schema: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse, fill declared defaults, and schema-validate model arguments."""

    if isinstance(raw_arguments, str):
        try:
            raw_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ToolValidationError("Tool arguments are not valid JSON") from exc
    if not isinstance(raw_arguments, dict):
        raise ToolValidationError("Tool arguments must be a JSON object")
    compiled = dict(defaults or {})
    compiled.update(raw_arguments)
    for name, definition in (schema.get("properties") or {}).items():
        if name not in compiled and isinstance(definition, dict) and "default" in definition:
            compiled[name] = definition["default"]
    validate_arguments(schema, compiled)
    return compiled


__all__ = ["compile_arguments"]
