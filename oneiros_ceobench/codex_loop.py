from __future__ import annotations

import importlib
import json
import os
import sys
import time
import tomllib
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .codex_events import codex_events_to_observed_messages, final_dashboard_message
from .oneiros_runtime import RunScopedOneiros
from .state import RunLayout
from .transcript_export import Message, write_observed_jsonl

if TYPE_CHECKING:
    from .config import RunConfig


class OneirosCodexLoop:
    def __init__(
        self,
        *,
        config: RunConfig,
        layout: RunLayout,
        codex_bin: str | None = None,
        oneiros_bin: str | None = None,
        max_resume_attempts_per_week: int = 3,
    ) -> None:
        self.config = config
        self.layout = layout
        self.codex_bin = codex_bin
        self.oneiros_bin = oneiros_bin or config.oneiros.bin
        self.max_resume_attempts_per_week = max_resume_attempts_per_week
        self.pipeline_log = layout.logs_dir / "pipeline.jsonl"

    def run(self, *, verbose: bool = True) -> dict[str, Any]:
        self.layout.mkdirs()
        self._apply_codex_env()
        self._ensure_ceobench_importable()
        _install_prompt_transform_fallback()
        module = cast(Any, importlib.import_module("saas_bench.agents.codex_agent.run_test"))
        base_cls = module.CodexCLIRunner
        runner_cls = self._build_runner_class(base_cls)
        runner = runner_cls(
            model=self.config.model.deployment or self.config.model.model_label,
            reasoning_effort=self.config.model.reasoning_effort,
            seed=self.config.run.seed,
            scenario=self.config.run.scenario,
            total_days=self.config.run.days,
            initial_cash=self.config.run.initial_cash,
            workspace_base=self.layout.ceobench_workspace,
            label=self.layout.run_dir.name,
            max_resume_attempts_per_week=self.max_resume_attempts_per_week,
            codex_bin=self.codex_bin,
        )

        self._log_pipeline(
            {
                "event": "run_start",
                "run_dir": str(self.layout.run_dir),
                "ceobench_workspace": str(self.layout.ceobench_workspace),
                "pipeline_log": str(self.pipeline_log),
            }
        )
        try:
            result = cast(dict[str, Any], runner.run(verbose=verbose))
        except Exception as exc:
            self._log_pipeline({"event": "run_error", "error": str(exc)})
            raise
        result_path = self.layout.run_dir / "run_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        self._log_pipeline({"event": "run_end", "result": result, "result_path": str(result_path)})
        return result

    def preview(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.layout.run_dir),
            "ceobench_src": str(self.config.paths.ceobench_repo / "src"),
            "ceobench_src_exists": (self.config.paths.ceobench_repo / "src").exists(),
            "codex_bin": self.codex_bin or os.environ.get("CODEX_BIN", "codex"),
            "oneiros_bin": self.oneiros_bin,
            "model": self.config.model.deployment or self.config.model.model_label,
            "reasoning_effort": self.config.model.reasoning_effort,
            "days": self.config.run.days,
            "seed": self.config.run.seed,
            "pipeline_log": str(self.pipeline_log),
            "codex_extra_args": self._codex_extra_args(),
        }

    def _build_runner_class(self, base_cls: type[Any]) -> type[Any]:
        harness = self

        class OneirosCodexRunner(base_cls):  # type: ignore[misc]
            def _codex_base_cmd(self) -> list[str]:
                cmd = super()._codex_base_cmd()
                cmd = _drop_config_override(cmd, "mcp_servers={}")
                cmd.extend(harness._codex_extra_args())
                return cmd

            def _write_agents_md(self) -> None:
                super()._write_agents_md()
                agents_path = self.agent_workspace / "AGENTS.md"
                ceobench_body = agents_path.read_text(encoding="utf-8")
                oneiros_body = harness._oneiros_agents_text()
                agents_path.write_text(
                    f"{oneiros_body}\n\n---\n\n{ceobench_body}",
                    encoding="utf-8",
                )

            def run(self, verbose: bool = True) -> dict[str, Any]:
                self.setup()

                status = self._get_game_status()
                sim_day = int(status.get("day", 0))
                if verbose:
                    print(f"\n{'=' * 60}")
                    print(f"Oneiros Codex Run - {self.run_id}")
                    print(
                        f"Model: {self.model} (effort={self.reasoning_effort}) "
                        f"| seed: {self.seed} | days: {self.total_days}"
                    )
                    print(f"Workspace: {self.workspace_dir}")
                    print(f"Pipeline log: {harness.pipeline_log}")
                    print(f"Start sim_day={sim_day} cash=${status.get('cash', 0):,.0f}")
                    print(f"{'=' * 60}\n", flush=True)

                game_outcome = None

                while sim_day < self.total_days:
                    week_idx = sim_day // 7 + 1
                    self._codex_session_id = None
                    week_messages: list[Message] = []
                    dashboard = self._get_dashboard()
                    base_prompt = (
                        f"Week {week_idx} (sim day {sim_day}). Dashboard:\n\n"
                        f"{dashboard}\n\n"
                        "Take whatever actions you decide on, then advance the week with "
                        "`./novamind-operation next-week \"<rationale>\" <12 cash forecasts>`. "
                        "Exit once next-week succeeds. AGENTS.md in this directory has full instructions."
                    )

                    harness._log_pipeline(
                        {
                            "event": "week_start",
                            "week": week_idx,
                            "sim_day": sim_day,
                        }
                    )
                    advanced = False
                    new_status: dict[str, Any] = status
                    for attempt in range(1, self.max_resume_attempts_per_week + 1):
                        resume = attempt > 1 and self._codex_session_id is not None
                        if verbose:
                            print(
                                f"\n--- week {week_idx} attempt {attempt} "
                                f"(sim_day={sim_day}, resume={resume}) ---",
                                flush=True,
                            )
                        prompt = (
                            base_prompt
                            if attempt == 1
                            else (
                                f"Sim day is still {sim_day}; you have not advanced the week. "
                                "Run `./novamind-operation next-week` with rationale + 12 cash "
                                "forecasts to advance, then stop."
                            )
                        )
                        result = self._call_codex(prompt, resume=resume)
                        week_messages.extend(
                            codex_events_to_observed_messages(
                                prompt=prompt,
                                events=result["events"],
                            )
                        )
                        if verbose:
                            print(
                                f"  codex exit={result['returncode']} "
                                f"elapsed={result['elapsed_s']:.1f}s "
                                f"events={len(result['events'])}",
                                flush=True,
                            )

                        new_status = self._get_game_status()
                        new_sim_day = int(new_status.get("day", sim_day))
                        self._log_event(
                            self.timing_log,
                            {
                                "timestamp": _now(),
                                "event": "codex_iteration",
                                "week": week_idx,
                                "attempt": attempt,
                                "sim_day_before": sim_day,
                                "sim_day_after": new_sim_day,
                                "codex_elapsed_s": round(result["elapsed_s"], 2),
                            },
                        )
                        harness._log_pipeline(
                            {
                                "event": "week_attempt",
                                "week": week_idx,
                                "attempt": attempt,
                                "sim_day_before": sim_day,
                                "sim_day_after": new_sim_day,
                                "codex_returncode": result["returncode"],
                                "codex_elapsed_s": round(result["elapsed_s"], 2),
                            }
                        )

                        if new_sim_day > sim_day:
                            advanced = True
                            sim_day = new_sim_day
                            cash = new_status.get("cash", 0)
                            if verbose:
                                print(
                                    f"  advanced to sim_day={sim_day} cash=${cash:,.0f}",
                                    flush=True,
                                )
                            self._commit_weeks_up_to(sim_day)
                            post_dashboard = self._get_dashboard()
                            dashboard_msg = final_dashboard_message(week_idx, post_dashboard)
                            if dashboard_msg is not None:
                                week_messages.append(dashboard_msg)
                            harness.ingest_successful_week(week_idx, week_messages, verbose=verbose)
                            break
                        if new_status.get("timed_out"):
                            print(f"\nstep_day timed out at sim_day={sim_day}", flush=True)
                            self._save_checkpoint(sim_day)
                            game_outcome = "timeout"
                            return cast(dict[str, Any], self._finalize(sim_day, game_outcome, verbose))

                    if not advanced:
                        if verbose:
                            print(
                                f"\nCould not advance week {week_idx} after "
                                f"{self.max_resume_attempts_per_week} attempts. Stopping.",
                                flush=True,
                            )
                        harness.write_partial_week(week_idx, week_messages)
                        game_outcome = "stalled"
                        break

                    cash = float(new_status.get("cash", 0))
                    if cash < 0:
                        if verbose:
                            print(f"\nBANKRUPT at sim_day={sim_day} (cash=${cash:,.0f})", flush=True)
                        game_outcome = "bankrupt"
                        self._save_checkpoint(sim_day)
                        break

                    self._save_checkpoint(sim_day)

                if not game_outcome:
                    game_outcome = "completed" if sim_day >= self.total_days else "incomplete"

                return cast(dict[str, Any], self._finalize(sim_day, game_outcome, verbose))

        return OneirosCodexRunner

    def ingest_successful_week(self, week: int, messages: list[Message], *, verbose: bool) -> None:
        observed_path = self.layout.weeks_dir / f"week_{week:03d}_observed.jsonl"
        write_observed_jsonl(messages, observed_path)
        runtime = RunScopedOneiros(self.layout, self.oneiros_bin)
        staged = runtime.stage_week(week=week, messages=messages, source_path=observed_path)
        log_path = runtime.extract_log_path(week)
        self._log_pipeline(
            {
                "event": "oneiros_extract_start",
                "week": week,
                "observed_transcript": str(observed_path),
                "staged_conversation": str(staged),
                "extract_log": str(log_path),
            }
        )
        if verbose:
            print(f"  observed transcript: {observed_path}", flush=True)
            print(f"  oneiros extraction log: {log_path}", flush=True)
            print(f"  tail with: tail -f {log_path}", flush=True)
        t0 = time.monotonic()
        proc = runtime.extract_week(week, check=False, record_to=log_path)
        elapsed = round(time.monotonic() - t0, 2)
        self._log_pipeline(
            {
                "event": "oneiros_extract_end",
                "week": week,
                "returncode": proc.returncode,
                "elapsed_s": elapsed,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            }
        )
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Oneiros extraction failed for week {week}; see {log_path}"
            )

    def write_partial_week(self, week: int, messages: list[Message]) -> Path | None:
        if not messages:
            return None
        partial_path = self.layout.weeks_dir / f"week_{week:03d}_partial.jsonl"
        write_observed_jsonl(messages, partial_path)
        self._log_pipeline(
            {
                "event": "partial_week_transcript",
                "week": week,
                "path": str(partial_path),
            }
        )
        return partial_path

    def _codex_config_args(self) -> list[str]:
        args = [
            "-c",
            f"mcp_servers={oneiros_mcp_toml(self.layout, self.oneiros_bin)}",
        ]
        if self.config.model.provider in {"azure", "azure_openai"}:
            args.extend(["-c", 'model_provider="azure"'])
            if self.config.azure_openai.endpoint:
                args.extend(
                    [
                        "-c",
                        f"model_providers.azure.base_url={_toml_string(self.config.azure_openai.endpoint)}",
                    ]
                )
            args.extend(["-c", 'model_providers.azure.name="Azure"'])
            args.extend(["-c", 'model_providers.azure.wire_api="responses"'])
            if self.config.azure_openai.api_version:
                args.extend(
                    [
                        "-c",
                        "model_providers.azure.query_params="
                        f'{{ "api-version" = {_toml_string(self.config.azure_openai.api_version)} }}',
                    ]
                )
            args.extend(
                [
                    "-c",
                    'model_providers.azure.env_http_headers={ "api-key" = "AZURE_OPENAI_API_KEY" }',
                ]
            )
            if self.config.azure_openai.ca_bundle:
                args.extend(
                    [
                        "-c",
                        f"model_providers.azure.tls_cert_path={_toml_string(self.config.azure_openai.ca_bundle)}",
                    ]
                )
        return args

    def _codex_extra_args(self) -> list[str]:
        return [
            "--disable",
            "plugins",
            "--disable",
            "computer_use",
            "--disable",
            "browser_use",
            "--disable",
            "in_app_browser",
            *self._codex_config_args(),
            *self._disable_existing_mcp_args(except_names={"oneiros"}),
        ]

    def _disable_existing_mcp_args(self, *, except_names: set[str]) -> list[str]:
        args: list[str] = []
        for name in _configured_mcp_server_names():
            if name in except_names:
                continue
            args.extend(["-c", f"mcp_servers.{_toml_key_segment(name)}.enabled=false"])
        return args

    def _apply_codex_env(self) -> None:
        env: dict[str, str] = {}
        if self.config.oneiros_azure is not None:
            env.update(self.config.oneiros_azure.env(include_secret=True))
        if self.config.azure_openai.endpoint:
            env.setdefault("AZURE_OPENAI_ENDPOINT", self.config.azure_openai.endpoint)
            env.setdefault("OPENAI_BASE_URL", self.config.azure_openai.endpoint)
        if self.config.model.deployment:
            env.setdefault("AZURE_OPENAI_DEPLOYMENT", self.config.model.deployment)
        if self.config.azure_openai.api_version:
            env.setdefault("AZURE_OPENAI_API_VERSION", self.config.azure_openai.api_version)
        if self.config.azure_openai.ca_bundle:
            env.setdefault("NODE_EXTRA_CA_CERTS", self.config.azure_openai.ca_bundle)
            env.setdefault("REQUESTS_CA_BUNDLE", self.config.azure_openai.ca_bundle)
            env.setdefault("SSL_CERT_FILE", self.config.azure_openai.ca_bundle)
        os.environ.update({key: value for key, value in env.items() if value})

    def _ensure_ceobench_importable(self) -> None:
        src_dir = self.config.paths.ceobench_repo / "src"
        if not src_dir.exists():
            raise FileNotFoundError(f"CEObench src directory not found: {src_dir}")
        src = str(src_dir)
        if src not in sys.path:
            sys.path.insert(0, src)

    def _oneiros_agents_text(self) -> str:
        prompt_path = self.layout.prompts_dir / "AGENTS.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").rstrip()
        return (Path(__file__).resolve().parents[1] / "prompts" / "AGENTS.md").read_text(
            encoding="utf-8"
        ).rstrip()

    def _log_pipeline(self, entry: dict[str, Any]) -> None:
        self.pipeline_log.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": _now(), **entry}
        with self.pipeline_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def oneiros_mcp_toml(layout: RunLayout, oneiros_bin: str) -> str:
    return (
        "{ "
        "oneiros = { "
        f"command = {_toml_string(oneiros_bin)}, "
        'args = ["mcp"], '
        'default_tools_approval_mode = "approve", '
        "env = { "
        f"ONEIROS_DB_PATH = {_toml_string(str(layout.oneiros_db))}, "
        f"ONEIROS_CONVERSATIONS_DIR = {_toml_string(str(layout.conversations_dir))} "
        "} "
        "} "
        "}"
    )


def _drop_config_override(cmd: list[str], exact_value: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(cmd):
        if cmd[i] == "-c" and i + 1 < len(cmd) and cmd[i + 1] == exact_value:
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _toml_key_segment(value: str) -> str:
    if value.replace("_", "").isalnum() and value[:1].isalpha():
        return value
    return json.dumps(value)


def _configured_mcp_server_names() -> list[str]:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return []
    try:
        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return []
    servers = cfg.get("mcp_servers")
    if not isinstance(servers, dict):
        return []
    return [str(name) for name in servers]


def _install_prompt_transform_fallback() -> None:
    module_name = "saas_bench.agents.claude_code.system_prompt_transform"
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    module.__dict__["build_claude_code_system_prompt"] = _build_ceobench_system_prompt
    sys.modules[module_name] = module


def _build_ceobench_system_prompt(bash_prompt: str, simulator_instructions: str) -> str:
    if "{simulator_instructions}" in bash_prompt:
        return bash_prompt.replace("{simulator_instructions}", simulator_instructions.strip())
    return f"{simulator_instructions.strip()}\n\n{bash_prompt.strip()}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
