from __future__ import annotations

import tomllib
from pathlib import Path

from oneiros_ceobench.codex_loop import (
    _build_ceobench_system_prompt,
    _toml_key_segment,
    oneiros_mcp_toml,
)
from oneiros_ceobench.state import RunLayout


def test_oneiros_mcp_toml_points_at_run_scoped_state(tmp_path: Path):
    layout = RunLayout.from_run_dir(tmp_path / "run")
    parsed = tomllib.loads(f"mcp_servers = {oneiros_mcp_toml(layout, 'oneiros-dev')}")

    server = parsed["mcp_servers"]["oneiros"]
    assert server["command"] == "oneiros-dev"
    assert server["args"] == ["mcp"]
    assert server["default_tools_approval_mode"] == "approve"
    assert server["env"]["ONEIROS_DB_PATH"] == str(layout.oneiros_db)
    assert server["env"]["ONEIROS_CONVERSATIONS_DIR"] == str(layout.conversations_dir)


def test_toml_key_segment_quotes_non_bare_keys():
    assert _toml_key_segment("node_repl") == "node_repl"
    assert _toml_key_segment("github-mcp") == '"github-mcp"'


def test_ceobench_system_prompt_fallback_inlines_simulator_instructions():
    prompt = "before\n{simulator_instructions}\nafter"

    assert _build_ceobench_system_prompt(prompt, "sim") == "before\nsim\nafter"
