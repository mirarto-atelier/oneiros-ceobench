from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .codex_loop import OneirosCodexLoop
from .config import RunConfig, load_config
from .oneiros_config import json_env, shell_exports
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

    doctor = sub.add_parser("doctor", help="Check resolved benchmark and Oneiros Azure settings.")
    doctor.add_argument("--config", type=Path, required=True)

    env_cmd = sub.add_parser("env", help="Print Azure/OpenAI environment derived from config.")
    env_cmd.add_argument("--config", type=Path, required=True)
    env_cmd.add_argument("--format", choices=["shell", "json"], default="shell")
    env_cmd.add_argument(
        "--include-secrets",
        action="store_true",
        help="Include API key values. Default output redacts secrets.",
    )

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

    run_codex = sub.add_parser(
        "run-codex",
        help="Run the CEObench Codex agent with run-scoped Oneiros memory.",
    )
    run_codex.add_argument("--config", type=Path, required=True)
    run_codex.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run_codex.add_argument("--run-id", default=None)
    run_codex.add_argument("--run-dir", type=Path, default=None)
    run_codex.add_argument("--codex-bin", default=None)
    run_codex.add_argument("--oneiros-bin", default=None)
    run_codex.add_argument("--max-resume-attempts-per-week", type=int, default=3)
    run_codex.add_argument("--quiet", action="store_true")
    run_codex.add_argument("--dry-run", action="store_true")

    aggregate = sub.add_parser("aggregate-results", help="Build docs/data/runs.json from compact results.")
    aggregate.add_argument("--results-dir", type=Path, default=Path("results"))
    aggregate.add_argument("--output", type=Path, default=Path("docs/data/runs.json"))

    args = parser.parse_args(argv)

    if args.command == "init":
        return _cmd_init(args.config, args.runs_dir, args.run_id)
    if args.command == "doctor":
        return _cmd_doctor(args.config)
    if args.command == "env":
        return _cmd_env(args.config, args.format, args.include_secrets)
    if args.command == "stage-week":
        return _cmd_stage_week(args.run_dir, args.week, args.jsonl)
    if args.command == "extract-week":
        return _cmd_extract_week(args.run_dir, args.week, args.oneiros_bin)
    if args.command == "ingest-week":
        staged = _cmd_stage_week(args.run_dir, args.week, args.jsonl)
        if staged != 0:
            return staged
        return _cmd_extract_week(args.run_dir, args.week, args.oneiros_bin)
    if args.command == "run-codex":
        return _cmd_run_codex(
            args.config,
            args.runs_dir,
            args.run_id,
            args.run_dir,
            args.codex_bin,
            args.oneiros_bin,
            args.max_resume_attempts_per_week,
            args.quiet,
            args.dry_run,
        )
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
    if config.oneiros_azure is not None:
        print(f"azure source: {config.oneiros_azure.source_path}")
        print(f"azure deployment: {config.model.deployment}")
    return 0


def _cmd_doctor(config_path: Path) -> int:
    config = load_config(config_path)
    print(f"config: {config_path.resolve()}")
    print(f"run: {config.run.days} days, seed={config.run.seed}, scenario={config.run.scenario}")
    print(f"model provider: {config.model.provider}")
    print(f"model deployment: {config.model.deployment or '(unset)'}")
    print(f"model label: {config.model.model_label}")
    print(f"azure source: {config.azure_openai.source}")
    print(f"azure endpoint: {config.azure_openai.endpoint or '(unset)'}")
    print(f"azure api version: {config.azure_openai.api_version or '(unset)'}")
    print(f"azure ca bundle: {config.azure_openai.ca_bundle or '(unset)'}")
    if config.azure_openai.ca_bundle:
        print(f"azure ca bundle exists: {Path(config.azure_openai.ca_bundle).expanduser().exists()}")
    if config.oneiros_azure is not None:
        settings = config.oneiros_azure
        print(f"oneiros config: {settings.source_path}")
        print(f"oneiros extractor provider: {settings.extractor_provider}")
        print(f"oneiros provider section: extractor.{settings.provider_section}")
        print(f"oneiros api key: {'set' if settings.api_key_set else 'missing'}")
    return 0


def _cmd_env(config_path: Path, output_format: str, include_secrets: bool) -> int:
    config = load_config(config_path)
    env: dict[str, str] = {}
    if config.oneiros_azure is not None:
        env.update(config.oneiros_azure.env(include_secret=include_secrets))
    else:
        if config.azure_openai.endpoint:
            env["AZURE_OPENAI_ENDPOINT"] = config.azure_openai.endpoint
            env["OPENAI_BASE_URL"] = config.azure_openai.endpoint
        if config.model.deployment:
            env["AZURE_OPENAI_DEPLOYMENT"] = config.model.deployment
        if config.azure_openai.api_version:
            env["AZURE_OPENAI_API_VERSION"] = config.azure_openai.api_version
        if config.azure_openai.ca_bundle:
            env["NODE_EXTRA_CA_CERTS"] = config.azure_openai.ca_bundle
            env["REQUESTS_CA_BUNDLE"] = config.azure_openai.ca_bundle
            env["SSL_CERT_FILE"] = config.azure_openai.ca_bundle

    if output_format == "json":
        print(json_env(env, redact_secrets=not include_secrets))
    else:
        print(shell_exports(env, redact_secrets=not include_secrets))
    return 0


def _cmd_run_codex(
    config_path: Path,
    runs_dir: Path,
    run_id: str | None,
    run_dir: Path | None,
    codex_bin: str | None,
    oneiros_bin: str | None,
    max_resume_attempts_per_week: int,
    quiet: bool,
    dry_run: bool,
) -> int:
    config = load_config(config_path)
    if run_dir is None:
        layout = create_run(config, runs_dir, run_id)
        _copy_oneiros_prompt(layout)
    else:
        layout = RunLayout.from_run_dir(run_dir)
        layout.mkdirs()
        if not (layout.run_dir / "manifest.json").exists():
            from .state import write_manifest

            write_manifest(layout, config)
        _copy_oneiros_prompt(layout)
    print(f"run dir: {layout.run_dir}", flush=True)
    print(f"pipeline log: {layout.logs_dir / 'pipeline.jsonl'}", flush=True)
    print(f"tail with: tail -f {layout.logs_dir / 'pipeline.jsonl'}", flush=True)
    loop = OneirosCodexLoop(
        config=config,
        layout=layout,
        codex_bin=codex_bin,
        oneiros_bin=oneiros_bin,
        max_resume_attempts_per_week=max_resume_attempts_per_week,
    )
    if dry_run:
        print(json.dumps(loop.preview(), indent=2, sort_keys=True))
        return 0
    proc = _run_codex_worker(
        config=config,
        layout=layout,
        codex_bin=codex_bin,
        oneiros_bin=oneiros_bin,
        max_resume_attempts_per_week=max_resume_attempts_per_week,
        quiet=quiet,
    )
    return proc.returncode


def _run_codex_worker(
    *,
    config: RunConfig,
    layout: RunLayout,
    codex_bin: str | None,
    oneiros_bin: str | None,
    max_resume_attempts_per_week: int,
    quiet: bool,
) -> subprocess.CompletedProcess[Any]:
    cmd = [
        "uv",
        "run",
        "--project",
        str(config.paths.ceobench_repo),
        "python",
        "-m",
        "oneiros_ceobench.codex_worker",
        "--run-dir",
        str(layout.run_dir),
        "--max-resume-attempts-per-week",
        str(max_resume_attempts_per_week),
    ]
    if codex_bin:
        cmd.extend(["--codex-bin", codex_bin])
    if oneiros_bin:
        cmd.extend(["--oneiros-bin", oneiros_bin])
    if quiet:
        cmd.append("--quiet")

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    if config.oneiros_azure is not None:
        env.update(config.oneiros_azure.env(include_secret=True))
    if not env.get("NMDB_KEY"):
        nmdb_key = _load_ceobench_embedded_key(config.paths.ceobench_repo)
        if nmdb_key:
            env["NMDB_KEY"] = nmdb_key
    package_root = str(Path(__file__).resolve().parents[1])
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        package_root if not existing_pythonpath else f"{package_root}{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(cmd, env=env, check=False)


def _load_ceobench_embedded_key(ceobench_repo: Path) -> str:
    key_path = ceobench_repo / "src" / "saas_bench" / "_embedded_key.py"
    if not key_path.exists():
        return ""
    spec = importlib.util.spec_from_file_location("_oneiros_ceobench_embedded_key", key_path)
    if spec is None or spec.loader is None:
        return ""
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = getattr(module, "_NMDB_KEY", "")
    return str(value) if value else ""


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


def _copy_oneiros_prompt(layout: RunLayout) -> None:
    prompt_src = Path(__file__).resolve().parents[1] / "prompts" / "AGENTS.md"
    prompt_dst = layout.prompts_dir / "AGENTS.md"
    shutil.copy2(prompt_src, prompt_dst)


def _cmd_extract_week(run_dir: Path, week: int, oneiros_bin: str | None) -> int:
    layout = RunLayout.from_run_dir(run_dir)
    runtime = RunScopedOneiros(layout, oneiros_bin or _manifest_oneiros_bin(run_dir) or "oneiros")
    log_path = runtime.extract_log_path(week)
    print(f"extraction log: {log_path}", flush=True)
    print(f"tail with: tail -f {log_path}", flush=True)
    try:
        proc = runtime.extract_week(week, check=False, record_to=log_path)
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
