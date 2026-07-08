from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

Message = dict[str, Any]


def load_observed_jsonl(path: Path) -> list[Message]:
    messages: list[Message] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
        if not isinstance(raw, dict):
            continue
        msg = normalize_message(raw)
        if msg is not None:
            messages.append(msg)
    return messages


def normalize_message(raw: dict[str, Any]) -> Message | None:
    role = str(raw.get("role", "")).lower()
    mapped_role = _map_role(role)
    if mapped_role is None:
        return None

    content = _stringify_content(raw.get("content", ""))
    if not content.strip():
        return None

    message: Message = {
        "role": mapped_role,
        "content": content,
        "timestamp": str(raw.get("timestamp") or _now()),
    }
    meta = {
        key: raw[key]
        for key in ("name", "tool_call_id", "tool_name")
        if key in raw and raw[key] is not None
    }
    if meta:
        message["meta"] = meta
    return message


def write_observed_jsonl(messages: list[Message], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for message in messages:
            fh.write(json.dumps(message, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def _map_role(role: str) -> str | None:
    if role in {"user", "assistant"}:
        return role
    if role in {"tool", "function", "tool_result"}:
        return "tool_result"
    if role in {"system", "developer"}:
        return None
    return None


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
