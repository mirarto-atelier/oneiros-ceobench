from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .config import RunConfig


@dataclass(frozen=True)
class RunLayout:
    run_dir: Path
    ceobench_workspace: Path
    oneiros_dir: Path
    oneiros_db: Path
    conversations_dir: Path
    fresh_dir: Path
    archive_dir: Path
    weeks_dir: Path
    logs_dir: Path
    prompts_dir: Path

    @classmethod
    def from_run_dir(cls, run_dir: Path) -> RunLayout:
        run_dir = run_dir.resolve()
        oneiros_dir = run_dir / "oneiros"
        conversations_dir = oneiros_dir / "conversations"
        return cls(
            run_dir=run_dir,
            ceobench_workspace=run_dir / "ceobench_workspace",
            oneiros_dir=oneiros_dir,
            oneiros_db=oneiros_dir / "oneiros.db",
            conversations_dir=conversations_dir,
            fresh_dir=conversations_dir / "fresh",
            archive_dir=conversations_dir / "archive",
            weeks_dir=run_dir / "weeks",
            logs_dir=run_dir / "logs",
            prompts_dir=run_dir / "prompts",
        )

    def mkdirs(self) -> None:
        for path in (
            self.ceobench_workspace,
            self.oneiros_dir,
            self.fresh_dir,
            self.archive_dir,
            self.weeks_dir,
            self.logs_dir,
            self.prompts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def default_run_id(config: RunConfig) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in config.name)
    safe_name = "-".join(part for part in safe_name.lower().split("-") if part)
    return f"{stamp}-{safe_name}"


def create_run(config: RunConfig, runs_dir: Path, run_id: str | None = None) -> RunLayout:
    run_id = run_id or default_run_id(config)
    layout = RunLayout.from_run_dir(runs_dir / run_id)
    layout.mkdirs()
    write_manifest(layout, config)
    return layout


def write_manifest(layout: RunLayout, config: RunConfig) -> None:
    config_payload = _jsonable(asdict(config))
    config_payload.pop("oneiros_azure", None)
    if config.oneiros_azure is not None:
        config_payload["inherited_oneiros_azure"] = config.oneiros_azure.public_dict()

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run_id": layout.run_dir.name,
        "config": config_payload,
        "paths": {
            "run_dir": str(layout.run_dir),
            "ceobench_workspace": str(layout.ceobench_workspace),
            "oneiros_db": str(layout.oneiros_db),
            "oneiros_conversations_dir": str(layout.conversations_dir),
        },
        "revisions": {
            "ceobench": git_revision(config.paths.ceobench_repo),
            "oneiros": git_revision(config.paths.oneiros_repo),
            "oneiros_ceobench": git_revision(Path(__file__).resolve().parents[1]),
        },
        "status": "initialized",
    }
    (layout.run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")))


def git_revision(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"path": str(path), "present": path.exists(), "git": False}
    commit = _git(path, "rev-parse", "HEAD")
    branch = _git(path, "branch", "--show-current")
    dirty = bool(_git(path, "status", "--porcelain"))
    return {
        "path": str(path),
        "git": True,
        "commit": commit or None,
        "branch": branch or None,
        "dirty": dirty,
    }


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
