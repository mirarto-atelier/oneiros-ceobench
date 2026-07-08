from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .transcript_export import Message, normalize_message


def codex_events_to_observed_messages(
    *,
    prompt: str,
    events: list[dict[str, Any]],
    timestamp: str | None = None,
) -> list[Message]:
    """Convert Codex JSONL events into Oneiros-ingestable observed messages."""
    ts = timestamp or _now()
    messages: list[Message] = []
    prompt_message = normalize_message(
        {
            "role": "user",
            "content": prompt,
            "timestamp": ts,
            "name": "ceobench-week-prompt",
        }
    )
    if prompt_message is not None:
        messages.append(prompt_message)

    for event in events:
        messages.extend(_event_to_messages(event))
    return messages


def final_dashboard_message(week: int, dashboard: str) -> Message | None:
    return normalize_message(
        {
            "role": "tool_result",
            "name": "ceobench-dashboard",
            "content": f"Post-next-week dashboard for week {week}:\n\n{dashboard}",
            "timestamp": _now(),
        }
    )


def _event_to_messages(event: dict[str, Any]) -> list[Message]:
    event_type = event.get("type")
    payload = event.get("payload")
    if event_type == "response_item" and isinstance(payload, dict):
        return _response_item_to_messages(payload, str(event.get("timestamp") or _now()))
    if event_type == "item.completed":
        item = event.get("item")
        if isinstance(item, dict):
            return _completed_item_to_messages(item, str(event.get("timestamp") or _now()))
    return []


def _response_item_to_messages(payload: dict[str, Any], timestamp: str) -> list[Message]:
    payload_type = payload.get("type")
    if payload_type == "message":
        role = str(payload.get("role") or "")
        if role == "user":
            return []
        return _single_message(
            role=role,
            content=_content_text(payload.get("content")),
            timestamp=timestamp,
        )
    if payload_type == "function_call":
        name = str(payload.get("name") or "tool")
        arguments = _json_or_text(payload.get("arguments"))
        return _single_message(
            role="assistant",
            content=f"Tool call: {name}\nArguments:\n{arguments}",
            timestamp=timestamp,
            tool_name=name,
        )
    if payload_type == "function_call_output":
        return _single_message(
            role="tool_result",
            content=_json_or_text(payload.get("output")),
            timestamp=timestamp,
            tool_call_id=_optional_str(payload.get("call_id")),
        )
    return []


def _completed_item_to_messages(item: dict[str, Any], timestamp: str) -> list[Message]:
    item_type = str(item.get("type") or "")
    if item_type in {"agent_message", "assistant_message", "message"}:
        role = str(item.get("role") or "assistant")
        if role == "user":
            return []
        return _single_message(
            role=role,
            content=_content_text(item.get("content")) or str(item.get("text") or ""),
            timestamp=timestamp,
        )
    if item_type in {"function_call", "tool_call"}:
        name = str(item.get("name") or item.get("tool_name") or "tool")
        return _single_message(
            role="assistant",
            content=f"Tool call: {name}\nArguments:\n{_json_or_text(item.get('arguments'))}",
            timestamp=timestamp,
            tool_name=name,
        )
    if item_type in {"function_call_output", "tool_call_output", "tool_result"}:
        return _single_message(
            role="tool_result",
            content=_json_or_text(item.get("output") or item.get("content")),
            timestamp=timestamp,
            tool_call_id=_optional_str(item.get("call_id")),
        )
    return []


def _single_message(
    *,
    role: str,
    content: str,
    timestamp: str,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> list[Message]:
    raw: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
    }
    if tool_name:
        raw["tool_name"] = tool_name
        raw["name"] = tool_name
    if tool_call_id:
        raw["tool_call_id"] = tool_call_id
    message = normalize_message(raw)
    return [message] if message is not None else []


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return _json_or_text(content)


def _json_or_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
