from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.tools.builtin import analyze_bidding, analyze_finance


class SandboxError(RuntimeError):
    pass


async def run_trusted_sandbox(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run only repository-owned deterministic analyzers in native development.

    Arbitrary model-authored Python is deliberately rejected until the secure
    container runner is installed.  Keeping this boundary explicit prevents a
    convenient local development switch from becoming remote code execution.
    """

    if not settings.allow_trusted_sandbox:
        raise SandboxError("SANDBOX_DISABLED")
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
    raise SandboxError("ARBITRARY_PYTHON_DISABLED_NATIVE_DEV")


async def run_arbitrary_python(code: str, *, workdir: Path) -> dict[str, Any]:
    if settings.is_native_dev or not settings.allow_arbitrary_python:
        raise SandboxError("ARBITRARY_PYTHON_DISABLED_NATIVE_DEV")
    if not code.strip():
        raise SandboxError("PYTHON_CODE_EMPTY")
    workdir.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        "python",
        "-I",
        "-c",
        code,
        cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=max(1, settings.sandbox_timeout_seconds)
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise SandboxError("SANDBOX_TIMEOUT") from exc
    if len(stdout) + len(stderr) > settings.sandbox_max_output_bytes:
        raise SandboxError("SANDBOX_OUTPUT_LIMIT")
    if process.returncode:
        raise SandboxError(stderr.decode("utf-8", errors="replace")[:2000])
    output = stdout.decode("utf-8", errors="replace")
    try:
        data: Any = json.loads(output) if output.strip() else None
    except json.JSONDecodeError:
        data = output
    return {"status": "success", "data": data}


__all__ = ["SandboxError", "run_arbitrary_python", "run_trusted_sandbox"]
