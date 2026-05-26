"""Chat task runner — agentic loop with tool calling.

Runs as an asyncio.Task. Streams deltas via Socket.IO, persists to DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from cptr.env import CHAT_MAX_ITERATIONS
from cptr.models import Chat, ChatMessage, Config
from cptr.socket.main import emit_to_user
from cptr.utils.ai import (
    ChatCompletionForm,
    stream_anthropic,
    stream_openai_completions,
    stream_openai_responses,
)
from cptr.utils.config import _get_jwt_secret, now_ms
from cptr.utils.crypto import decrypt_key
from cptr.utils.tools import TOOLS, execute_tool, get_tool_list
from cptr.utils.chat_export import export_chat_to_file

logger = logging.getLogger(__name__)

# ── Task registry ───────────────────────────────────────────

_tasks: dict[str, asyncio.Task] = {}  # message_id → asyncio.Task
_task_state: dict[str, dict] = {}     # message_id → {content, output}


def start_task(
    message_id: str,
    chat_id: str,
    user_id: str,
    connection: dict,
    workspace: str,
    model: str,
):
    """Launch the agentic loop as a background asyncio.Task."""
    task = asyncio.create_task(
        run_chat_task(message_id, chat_id, user_id, connection, workspace, model)
    )
    _tasks[message_id] = task


async def cancel_task(message_id: str) -> bool:
    """Cancel a running task. Returns True if found."""
    task = _tasks.get(message_id)
    if task:
        task.cancel()
        return True
    return False


def is_running(message_id: str) -> bool:
    """Check if a task is currently running."""
    task = _tasks.get(message_id)
    return task is not None and not task.done()


def get_live_state(message_id: str) -> dict | None:
    """Get live in-memory state for a running task."""
    return _task_state.get(message_id)


# ── System prompt ───────────────────────────────────────────


def _get_file_tree(workspace: str, max_entries: int = 200) -> str:
    """Generate a compact file tree listing for the workspace."""
    ws = Path(workspace)
    if not ws.is_dir():
        return ""
    ignore = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next",
              "build", "dist", ".cptr", ".svelte-kit", ".DS_Store"}
    entries = []
    for item in sorted(ws.iterdir()):
        if item.name in ignore:
            continue
        suffix = "/" if item.is_dir() else ""
        entries.append(f"  {item.name}{suffix}")
        if item.is_dir():
            try:
                for child in sorted(item.iterdir()):
                    if child.name in ignore:
                        continue
                    csuffix = "/" if child.is_dir() else ""
                    entries.append(f"    {child.name}{csuffix}")
                    if len(entries) >= max_entries:
                        entries.append("    ...")
                        break
            except PermissionError:
                pass
        if len(entries) >= max_entries:
            break
    return "\n".join(entries)


def _load_system_prompt(workspace: str) -> str:
    """Load system prompt: .cptr/system.md → default. Appends file tree."""
    ws_prompt = Path(workspace) / ".cptr" / "system.md"
    if ws_prompt.is_file():
        base = ws_prompt.read_text(errors="replace").strip()
    else:
        base = (
            "You are a helpful coding assistant. "
            "You have access to tools to read, search, and modify files in the workspace. "
            "Use them to help the user with their coding tasks."
        )

    tree = _get_file_tree(workspace)
    if tree:
        base += f"\n\nWorkspace: {Path(workspace).name}\nFiles:\n{tree}"

    return base



# ── Message history ─────────────────────────────────────────


async def _load_message_history(chat_id: str) -> list[dict]:
    """Load chat messages as canonical dicts for the LLM."""
    messages = await ChatMessage.get_all_by_chat(chat_id)
    result = []
    for m in messages:
        # Skip in-progress assistant placeholders (empty, not done)
        if m.role == "assistant" and not m.done:
            continue
        entry: dict = {"role": m.role, "content": m.content or ""}

        # Reconstruct tool calls from output items for the provider
        if m.output:
            tool_calls = []
            for item in m.output:
                if item.get("type") == "function_call" and item.get("status") == "completed":
                    tool_calls.append({
                        "id": item["call_id"],
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "arguments": json.dumps(item.get("arguments", {})),
                        },
                    })
            if tool_calls:
                entry["tool_calls"] = tool_calls

            # Add tool results as separate messages
            for item in m.output:
                if item.get("type") == "function_call_output":
                    result.append(entry)
                    entry = {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": item.get("output", ""),
                    }

        result.append(entry)
    return result


def _append_tool_to_messages(
    messages: list[dict], event: dict, result: str, provider: str
):
    """Append a tool call + result to the message history for the next API call."""
    # Add assistant message with tool_call
    messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": event["call_id"],
            "type": "function",
            "function": {
                "name": event["name"],
                "arguments": json.dumps(event["arguments"]),
            },
        }],
    })
    # Add tool result
    messages.append({
        "role": "tool",
        "tool_call_id": event["call_id"],
        "content": result,
    })


# ── Connection resolution ───────────────────────────────────


def _default_base_url(provider: str) -> str:
    return {
        "anthropic": "https://api.anthropic.com/v1",
        "openai": "https://api.openai.com/v1",
    }.get(provider, "https://api.openai.com/v1")


# ── The agentic loop ────────────────────────────────────────


async def run_chat_task(
    message_id: str,
    chat_id: str,
    user_id: str,
    connection: dict,
    workspace: str,
    model: str,
):
    """Plain async function. Makes raw API calls in a loop."""

    async def emit(**data):
        """Stream an output delta to the user."""
        await emit_to_user(
            user_id, {"chat_id": chat_id, "message_id": message_id, **data}
        )

    # Load existing state so continuations don't overwrite previous output
    msg = await ChatMessage.get_by_id(message_id)
    content = (msg.content or "") if msg else ""
    output_items: list[dict] = list(msg.output or []) if msg else []
    text_buffer = ""  # Accumulates text between tool calls

    logger.info("[task %s] start — existing content=%d chars, output=%d items",
                message_id[:8], len(content), len(output_items))

    def _flush_text():
        """Flush accumulated text into a message output item."""
        nonlocal text_buffer
        if not text_buffer:
            return
        logger.info("[task %s] flush_text — %d chars into message item",
                    message_id[:8], len(text_buffer))
        output_items.append({
            "type": "message",
            "id": str(uuid.uuid4()),
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text_buffer}],
        })
        text_buffer = ""

    def _sync_state():
        """Update in-memory state so API can serve it on refresh."""
        _task_state[message_id] = {"content": content, "output": output_items}

    try:
        provider = connection["provider"]
        api_key = decrypt_key(connection.get("api_key", ""), _get_jwt_secret())
        base_url = connection.get("base_url") or _default_base_url(provider)

        system = _load_system_prompt(workspace)
        messages = await _load_message_history(chat_id)
        tools = get_tool_list()

        # Check if user enabled auto-approve for all tools
        chat_obj = await Chat.get_by_id(chat_id)
        chat_params = (
            (chat_obj.meta or {}).get("params", {}) if chat_obj else {}
        )
        auto_approve_all = bool(chat_params.get("auto_approve_tools"))

        for _iteration in range(CHAT_MAX_ITERATIONS):
            form_data = ChatCompletionForm(
                model=model,
                messages=messages,
                instructions=system,
                tools=tools,
            )

            if provider == "anthropic":
                stream = stream_anthropic(form_data, base_url, api_key)
            elif connection.get("api_type") == "responses":
                stream = stream_openai_responses(form_data, base_url, api_key)
            else:
                stream = stream_openai_completions(form_data, base_url, api_key)

            restart = False

            async for event in stream:
                if event["type"] == "text_delta":
                    content += event["content"]
                    text_buffer += event["content"]
                    await emit(delta=event["content"])
                    _sync_state()

                elif event["type"] == "tool_call":
                    # Flush any text before the tool call
                    _flush_text()

                    name = event["name"]
                    tool = TOOLS.get(name)
                    item = {
                        "type": "function_call",
                        "id": str(uuid.uuid4()),
                        "call_id": event["call_id"],
                        "name": name,
                        "arguments": event["arguments"],
                    }

                    if tool and (tool["auto"] or auto_approve_all):
                        result = await execute_tool(name, event["arguments"], workspace)
                        item["status"] = "completed"
                        output_items.append(item)
                        result_item = {
                            "type": "function_call_output",
                            "call_id": event["call_id"],
                            "output": result,
                        }
                        output_items.append(result_item)
                        await emit(output=item)
                        await emit(output=result_item)
                        _sync_state()

                        # Append to messages for next iteration
                        _append_tool_to_messages(messages, event, result, provider)
                        restart = True
                        break

                    else:
                        # Needs approval — persist and stop
                        item["status"] = "pending"
                        output_items.append(item)
                        await ChatMessage.update(
                            message_id,
                            content=content,
                            output=output_items,
                            done=False,
                        )
                        await emit(output=item)
                        await emit(done=True)
                        return

                elif event["type"] == "usage":
                    _flush_text()
                    usage = {k: v for k, v in event.items() if k != "type"}
                    logger.info("[task %s] save (usage) — content=%d chars, output=%d items, types=%s",
                                message_id[:8], len(content), len(output_items),
                                [i.get('type') for i in output_items])
                    await ChatMessage.update(
                        message_id,
                        content=content,
                        output=output_items,
                        usage=usage,
                        done=True,
                    )
                    await emit(done=True)
                    return

                elif event["type"] == "done":
                    # Stream ended without explicit usage
                    pass

            if not restart:
                _flush_text()
                logger.info("[task %s] save (end) — content=%d chars, output=%d items, types=%s",
                            message_id[:8], len(content), len(output_items),
                            [i.get('type') for i in output_items])
                await ChatMessage.update(
                    message_id,
                    content=content,
                    output=output_items,
                    done=True,
                )
                await emit(done=True)
                return

        # Max iterations reached
        await ChatMessage.update(
            message_id,
            content=content,
            output=output_items,
            done=True,
            meta={"error": "max iterations reached"},
        )
        await emit(done=True)

    except asyncio.CancelledError:
        await ChatMessage.update(
            message_id, content=content, output=output_items, done=True
        )
        await emit(done=True)
    except Exception as e:
        logger.exception(f"Chat task error for message {message_id}")
        await ChatMessage.update(
            message_id,
            content=content,
            output=output_items,
            done=True,
            meta={"error": str(e)},
        )
        await emit(done=True)
    finally:
        _tasks.pop(message_id, None)
        _task_state.pop(message_id, None)
        try:
            await export_chat_to_file(chat_id)
        except Exception:
            logger.exception(f"Failed to export chat {chat_id}")
