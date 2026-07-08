from __future__ import annotations

from oneiros_ceobench.codex_events import codex_events_to_observed_messages


def test_codex_events_to_observed_messages_captures_tools_without_env_context():
    messages = codex_events_to_observed_messages(
        prompt="Week 1 dashboard",
        timestamp="2026-07-08T00:00:00Z",
        events=[
            {
                "timestamp": "2026-07-08T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "<environment_context>"}],
                },
            },
            {
                "timestamp": "2026-07-08T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"command":["./novamind-operation","next-week"]}',
                    "call_id": "call_1",
                },
            },
            {
                "timestamp": "2026-07-08T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "=== Week 2 Dashboard ===",
                },
            },
            {
                "timestamp": "2026-07-08T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Advanced."}],
                },
            },
        ],
    )

    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "tool_result",
        "assistant",
    ]
    assert messages[0]["content"] == "Week 1 dashboard"
    assert "novamind-operation" in messages[1]["content"]
    assert messages[2]["meta"]["tool_call_id"] == "call_1"
