from __future__ import annotations

import json
import subprocess
from pathlib import Path

from oneiros_ceobench.oneiros_runtime import RunScopedOneiros
from oneiros_ceobench.state import RunLayout


def test_stage_week_writes_run_scoped_fresh_doc(tmp_path: Path):
    layout = RunLayout.from_run_dir(tmp_path / "run")
    layout.mkdirs()
    runtime = RunScopedOneiros(layout)

    out = runtime.stage_week(
        week=1,
        messages=[
            {
                "role": "user",
                "content": "dashboard",
                "timestamp": "2026-07-08T00:00:00Z",
            }
        ],
    )

    assert out == layout.fresh_dir / "ceobench-week-001.json"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["id"] == "ceobench-week-001"
    assert doc["messages"][0]["content"] == "dashboard"
    assert doc["source"]["adapter"] == "oneiros-ceobench"


def test_env_points_oneiros_at_run_state(tmp_path: Path):
    layout = RunLayout.from_run_dir(tmp_path / "run")
    env = RunScopedOneiros(layout, "oneiros-dev").env()

    assert env["ONEIROS_DB_PATH"] == str(layout.oneiros_db)
    assert env["ONEIROS_CONVERSATIONS_DIR"] == str(layout.conversations_dir)
    assert env["ONEIROS_BIN"] == "oneiros-dev"


def test_extract_log_path_is_week_scoped(tmp_path: Path):
    layout = RunLayout.from_run_dir(tmp_path / "run")
    runtime = RunScopedOneiros(layout)

    assert runtime.extract_log_path(12) == layout.logs_dir / "week_012_extract.jsonl"


def test_extract_week_uses_oneiros_record_to(tmp_path: Path, monkeypatch):
    layout = RunLayout.from_run_dir(tmp_path / "run")
    runtime = RunScopedOneiros(layout, "oneiros-test")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("oneiros_ceobench.oneiros_runtime.subprocess.run", fake_run)

    proc = runtime.extract_week(3, check=False)

    log_path = layout.logs_dir / "week_003_extract.jsonl"
    assert proc.returncode == 0
    assert log_path.exists()
    assert calls[0][0] == [
        "oneiros-test",
        "extract",
        "--session",
        "ceobench-week-003",
        "--record-to",
        str(log_path),
    ]
