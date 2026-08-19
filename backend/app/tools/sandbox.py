from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.tools.builtin import analyze_bidding, analyze_finance


class SandboxError(RuntimeError):
    pass


_SAFE_BUILTINS = {
    "abs": abs,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "dict": dict,
    "max": max,
    "min": min,
    "round": round,
    "sorted": sorted,
    "str": str,
    "sum": sum,
}
_SAFE_NODES = {
    ast.Module,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.If,
    ast.For,
    ast.Call,
    ast.Expr,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
}


def _validate_safe_code(code: str) -> None:
    if len(code.encode("utf-8")) > 50_000:
        raise SandboxError("PYTHON_CODE_LIMIT")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError("PYTHON_SYNTAX_ERROR") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 5_000:
        raise SandboxError("PYTHON_AST_LIMIT")
    for node in nodes:
        if type(node) not in _SAFE_NODES:
            raise SandboxError(f"PYTHON_NODE_NOT_ALLOWED:{type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise SandboxError("PYTHON_DUNDER_NOT_ALLOWED")
        if isinstance(node, ast.Call):
            # Calls are only accepted for the small, pure builtin allowlist.
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_BUILTINS:
                raise SandboxError("PYTHON_CALL_NOT_ALLOWED")


async def run_safe_python(
    code: str, *, data: Any = None, workdir: Path | None = None
) -> dict[str, Any]:
    """Execute a bounded data transformation without imports, files or network.

    This is the native-development Python capability. It intentionally is not a
    general Python interpreter: code can only read `data`, assign `result`, use
    pure builtins, and perform expression/loop transformations. The secure
    release sandbox can later replace this adapter without changing ToolSpec.
    """

    _validate_safe_code(code)
    if workdir is None:
        workdir = settings.local_storage_root / "sandbox"
    workdir.mkdir(parents=True, exist_ok=True)
    wrapper = (
        "import builtins as _builtins, json, sys\n"
        "payload = json.load(sys.stdin)\n"
        f"code = {json.dumps(code, ensure_ascii=False)}\n"
        f"allowed = {json.dumps(sorted(_SAFE_BUILTINS))}\n"
        "builtins = {name: getattr(_builtins, name) for name in allowed}\n"
        "scope = {'data': payload.get('data'), 'result': None}\n"
        "exec(compile(code, '<safe-sandbox>', 'exec'), {'__builtins__': builtins}, scope)\n"
        "print(json.dumps(scope.get('result'), ensure_ascii=False, default=str))\n"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-S",
        "-c",
        wrapper,
        cwd=str(workdir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    request_body = json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")
    if len(request_body) > settings.sandbox_max_output_bytes:
        raise SandboxError("SANDBOX_INPUT_LIMIT")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(request_body), timeout=max(1, settings.sandbox_timeout_seconds)
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise SandboxError("SANDBOX_TIMEOUT") from exc
    if len(stdout) + len(stderr) > settings.sandbox_max_output_bytes:
        raise SandboxError("SANDBOX_OUTPUT_LIMIT")
    if process.returncode:
        raise SandboxError(stderr.decode("utf-8", errors="replace")[:2_000])
    try:
        result = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise SandboxError("SANDBOX_INVALID_RESULT") from exc
    return {"status": "success", "data": result}


async def run_trusted_sandbox(
    operation: str, arguments: dict[str, Any], *, workdir: Path | None = None
) -> dict[str, Any]:
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
    if operation == "python.safe":
        return await run_safe_python(
            str(arguments.get("code", "")),
            data=arguments.get("data"),
            workdir=workdir,
        )
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


__all__ = [
    "SandboxError",
    "run_arbitrary_python",
    "run_safe_python",
    "run_trusted_sandbox",
]
