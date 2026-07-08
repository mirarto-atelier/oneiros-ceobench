from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .state import RunLayout

_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class RunScopedOneiros:
    def __init__(self, layout: RunLayout, oneiros_bin: str = "oneiros") -> None:
        self.layout = layout
        self.oneiros_bin = oneiros_bin

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["ONEIROS_DB_PATH"] = str(self.layout.oneiros_db)
        env["ONEIROS_CONVERSATIONS_DIR"] = str(self.layout.conversations_dir)
        env["ONEIROS_BIN"] = self.oneiros_bin
        return env

    def week_session_id(self, week: int) -> str:
        if week < 1:
            raise ValueError("week must be >= 1")
        return f"ceobench-week-{week:03d}"

    def stage_week(
        self,
        *,
        week: int,
        messages: list[dict[str, Any]],
        source_path: Path | None = None,
    ) -> Path:
        session_id = self.week_session_id(week)
        if not _SAFE_SESSION_ID.match(session_id):
            raise ValueError(f"unsafe session id: {session_id!r}")
        if not messages:
            raise ValueError("cannot stage a week with zero observed messages")

        doc = {
            "id": session_id,
            "name": f"CEO-Bench observed week {week:03d}",
            "messages": messages,
            "date": _derive_date(messages),
            "agentSessionId": session_id,
            "isRunning": False,
            "_location": "fresh",
            "source": {
                "adapter": "oneiros-ceobench",
                "week": week,
                "source_path": str(source_path) if source_path else None,
            },
        }

        self.layout.fresh_dir.mkdir(parents=True, exist_ok=True)
        out = self.layout.fresh_dir / f"{session_id}.json"
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def extract_log_path(self, week: int) -> Path:
        if week < 1:
            raise ValueError("week must be >= 1")
        return self.layout.logs_dir / f"week_{week:03d}_extract.jsonl"

    def extract_week(
        self,
        week: int,
        *,
        check: bool = True,
        record_to: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        session_id = self.week_session_id(week)
        record_to = record_to or self.extract_log_path(week)
        record_to.parent.mkdir(parents=True, exist_ok=True)
        record_to.touch(mode=0o600, exist_ok=True)
        return subprocess.run(
            [
                self.oneiros_bin,
                "extract",
                "--session",
                session_id,
                "--record-to",
                str(record_to),
            ],
            env=self.env(),
            cwd=str(self.layout.run_dir),
            capture_output=True,
            text=True,
            check=check,
        )


def _derive_date(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        ts = str(message.get("timestamp") or "")
        if len(ts) >= 10:
            return ts[:10]
    return datetime.now(UTC).date().isoformat()
