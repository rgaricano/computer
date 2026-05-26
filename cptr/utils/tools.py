"""Tool definitions — plain functions with schema introspection.

Tools are real async functions. Schemas are auto-generated from
type hints + docstrings via inspect. The LLM never sees the
`workspace` parameter — it's injected by the task runner.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import get_type_hints


# ── Tool functions ──────────────────────────────────────────


async def read_file(path: str, *, workspace: str) -> str:
    """Read file contents, capped at 100KB.
    :param path: Path relative to workspace root.
    """
    full = _resolve_path(path, workspace)
    if not full.is_file():
        return f"Error: file not found: {path}"
    size = full.stat().st_size
    if size > 100_000:
        return f"Error: file too large ({size} bytes, max 100KB)"
    return full.read_text(errors="replace")


async def list_directory(path: str = ".", recursive: bool = False, *, workspace: str) -> str:
    """List files and directories, excluding .git, node_modules, etc.
    :param path: Directory path relative to workspace root.
    :param recursive: Whether to list recursively.
    """
    full = _resolve_path(path, workspace)
    if not full.is_dir():
        return f"Error: not a directory: {path}"

    ignore = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "build", "dist"}
    entries = []

    if recursive:
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if d not in ignore]
            rel = Path(root).relative_to(full)
            for f in files:
                entries.append(str(rel / f))
            if len(entries) > 500:
                entries.append("... (truncated at 500)")
                break
    else:
        for item in sorted(full.iterdir()):
            if item.name in ignore:
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(f"{item.name}{suffix}")

    return "\n".join(entries) if entries else "(empty directory)"


async def search_files(query: str, path: str = ".", *, workspace: str) -> str:
    """Grep workspace for a pattern, capped at 50 results.
    :param query: Search pattern (plain text).
    :param path: Directory to search in.
    """
    full = _resolve_path(path, workspace)
    if not full.is_dir():
        return f"Error: not a directory: {path}"

    results = []
    ignore = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    for root, dirs, files in os.walk(full):
        dirs[:] = [d for d in dirs if d not in ignore]
        for fname in files:
            fpath = Path(root) / fname
            try:
                text = fpath.read_text(errors="replace")
            except (OSError, PermissionError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if query in line:
                    rel = fpath.relative_to(full)
                    results.append(f"{rel}:{i}: {line.strip()}")
                    if len(results) >= 50:
                        results.append("... (truncated at 50 matches)")
                        return "\n".join(results)
    return "\n".join(results) if results else "No matches found."


async def write_file(path: str, content: str, *, workspace: str) -> str:
    """Write or create a file.
    :param path: Path relative to workspace root.
    :param content: File contents to write.
    """
    full = _resolve_path(path, workspace)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return f"Wrote {len(content)} bytes to {path}"


async def run_command(command: str, cwd: str = ".", *, workspace: str) -> str:
    """Run a shell command (30s timeout).
    :param command: The shell command to execute.
    :param cwd: Working directory relative to workspace root.
    """
    work_dir = _resolve_path(cwd, workspace)
    if not work_dir.is_dir():
        return f"Error: not a directory: {cwd}"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(work_dir),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace").strip()
        if proc.returncode != 0:
            return f"Exit code {proc.returncode}\n{output}"
        return output or "(no output)"
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: command timed out after 30s"
    except Exception as e:
        return f"Error: {e}"


# ── Path safety ──────────────────────────────────────────────


def _resolve_path(path: str, workspace: str) -> Path:
    """Resolve a relative path within the workspace. Rejects traversal."""
    ws = Path(workspace).resolve()
    full = (ws / path).resolve()
    if not str(full).startswith(str(ws)):
        raise ValueError(f"Path traversal rejected: {path}")
    return full


# ── Registry ────────────────────────────────────────────────

TOOLS: dict[str, dict] = {
    "read_file":      {"fn": read_file,      "auto": True},
    "list_directory":  {"fn": list_directory,  "auto": True},
    "search_files":    {"fn": search_files,    "auto": True},
    "write_file":      {"fn": write_file,      "auto": False},
    "run_command":     {"fn": run_command,     "auto": False},
}


# ── Schema from function signature ──────────────────────────

_TYPE_MAP = {str: "string", int: "integer", bool: "boolean", float: "number"}


def _fn_to_schema(name: str, fn) -> dict:
    """Introspect function → {name, description, parameters} for LLM."""
    doc = inspect.getdoc(fn) or ""
    description = doc.split("\n")[0]
    hints = get_type_hints(fn)
    sig = inspect.signature(fn)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "workspace":
            continue
        ptype = _TYPE_MAP.get(hints.get(pname), "string")  # type: ignore[arg-type]
        properties[pname] = {"type": ptype}
        # keyword-only with no default → required
        if param.default is inspect.Parameter.empty and param.kind != inspect.Parameter.KEYWORD_ONLY:
            required.append(pname)
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def get_tool_list() -> list[dict]:
    """Return tool schemas for the LLM."""
    return [_fn_to_schema(name, t["fn"]) for name, t in TOOLS.items()]


async def execute_tool(name: str, args: dict, workspace: str) -> str:
    """Execute a tool by name. Returns output string."""
    info = TOOLS.get(name)
    if not info:
        return f"Error: unknown tool: {name}"
    fn = info["fn"]
    try:
        return await fn(**args, workspace=workspace)
    except Exception as e:
        return f"Error executing {name}: {e}"
