from __future__ import annotations

from pathlib import Path

from oneiros_ceobench.transcript_export import load_observed_jsonl


def test_load_observed_jsonl_drops_system_and_maps_tool(tmp_path: Path):
    transcript = tmp_path / "week.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"role":"system","content":"hidden"}',
                '{"role":"user","content":"dashboard","timestamp":"2026-07-08T00:00:00Z"}',
                '{"role":"tool","name":"novamind-operation","content":"next-week ok"}',
            ]
        ),
        encoding="utf-8",
    )

    messages = load_observed_jsonl(transcript)

    assert [message["role"] for message in messages] == ["user", "tool_result"]
    assert messages[1]["meta"]["name"] == "novamind-operation"
