from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .config import load_config
from .oneiros_runtime import RunScopedOneiros
from .results import aggregate_results
from .state import RunLayout, create_run
from .transcript_export import load_observed_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oneiros-ceobench")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create an isolated benchmark run directory.")
    init.add_argument("--config", type=Path, required=True)
    init.add_argument("--runs-dir", type=Path, default=Path("runs"))
    init.add_argument("--run-id", default=None)

    stage = sub.add_parser("stage-week", help="Stage an observed weekly JSONL transcript.")
    stage.add_argument("--run-dir", type=Path, required=True)
    stage.add_argument("--week", type=int, required=True)
    stage.add_argument("--jsonl", type=Path, required=True)

    extract = sub.add_parser("extract-week", help="Run Oneiros extraction for a staged week.")
    extract.add_argument("--run-dir", type=Path, required=True)
    extract.add_argument("--week", type=int, required=True)
    extract.add_argument("--oneiros-bin", default=None)

    ingest = sub.add_parser("ingest-week", help="Stage and synchronously extract a weekly JSONL transcript.")
    ingest.add_argument("--run-dir", type=Path, required=True)
    ingest.add_argument("--week", type=int, required=True)
    ingest.add_argument("--jsonl", type=Path, required=True)
    ingest.add_argument("--oneiros-bin", default=None)

    aggregate = sub.add_parser("aggregate-results", help="Build docs/data/runs.json from compact results.")
    aggregate.add_argument("--results-dir", type=Path, default=Path("results"))
    aggregate.add_argument("--output", type=Path, default=Path("docs/data/runs.json"))

    args = parser.parse_args(argv)

    if args.command == "init":
        return _cmd_init(args.config, args.runs_dir, args.run_id)
    if args.command == "stage-week":
        return _cmd_stage_week(args.run_dir, args.week, args.jsonl)
    if args.command == "extract-week":
        return _cmd_extract_week(args.run_dir, args.week, args.oneiros_bin)
    if args.command == "ingest-week":
        staged = _cmd_stage_week(args.run_dir, args.week, args.jsonl)
        if staged != 0:
            return staged
        return _cmd_extract_week(args.run_dir, args.week, args.oneiros_bin)
    if args.command == "aggregate-results":
        payload = aggregate_results(args.results_dir, args.output)
        print(f"wrote {args.output} with {len(payload['runs'])} run(s)")
        return 0
    raise AssertionError(args.command)


def _cmd_init(config_path: Path, runs_dir: Path, run_id: str | None) -> int:
    config = load_config(config_path)
    layout = create_run(config, runs_dir, run_id)
    prompt_src = Path(__file__).resolve().parents[1] / "prompts" / "AGENTS.md"
    prompt_dst = layout.prompts_dir / "AGENTS.md"
    shutil.copy2(prompt_src, prompt_dst)
    print(f"created run: {layout.run_dir}")
    print(f"oneiros db: {layout.oneiros_db}")
    print(f"oneiros conversations: {layout.conversations_dir}")
    return 0


def _cmd_stage_week(run_dir: Path, week: int, jsonl_path: Path) -> int:
    layout = RunLayout.from_run_dir(run_dir)
    layout.mkdirs()
    messages = load_observed_jsonl(jsonl_path)
    week_copy = layout.weeks_dir / f"week_{week:03d}_observed.jsonl"
    shutil.copy2(jsonl_path, week_copy)
    staged = RunScopedOneiros(layout).stage_week(
        week=week,
        messages=messages,
        source_path=week_copy,
    )
    print(f"staged week {week}: {staged}")
    return 0


def _cmd_extract_week(run_dir: Path, week: int, oneiros_bin: str | None) -> int:
    layout = RunLayout.from_run_dir(run_dir)
    runtime = RunScopedOneiros(layout, oneiros_bin or _manifest_oneiros_bin(run_dir) or "oneiros")
    try:
        proc = runtime.extract_week(week, check=False)
    except FileNotFoundError:
        print(f"oneiros binary not found: {runtime.oneiros_bin}", file=sys.stderr)
        return 127
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def _manifest_oneiros_bin(run_dir: Path) -> str | None:
    manifest = run_dir / "manifest.json"
    if not manifest.exists():
        return None
    import json

    data = json.loads(manifest.read_text(encoding="utf-8"))
    config = data.get("config") or {}
    oneiros = config.get("oneiros") or {}
    value = oneiros.get("bin")
    return str(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
