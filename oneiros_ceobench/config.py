from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _expand_env_string(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        default = match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        return match.group(0)

    return _ENV_RE.sub(replace, value)


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_string(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class BenchmarkRun:
    days: int
    seed: int
    scenario: str
    initial_cash: float


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model_label: str
    deployment: str
    reasoning_effort: str


@dataclass(frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key_env: str
    api_version: str


@dataclass(frozen=True)
class PathConfig:
    ceobench_repo: Path
    oneiros_repo: Path


@dataclass(frozen=True)
class OneirosConfig:
    bin: str
    memory_mode: str
    ingest_hidden_state: bool


@dataclass(frozen=True)
class RunConfig:
    name: str
    description: str
    run: BenchmarkRun
    model: ModelConfig
    azure_openai: AzureOpenAIConfig
    paths: PathConfig
    oneiros: OneirosConfig
    raw: dict[str, Any]


def load_config(path: Path) -> RunConfig:
    path = path.resolve()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    data = expand_env(data)
    base = path.parent

    run = data.get("run") or {}
    model = data.get("model") or {}
    azure = data.get("azure_openai") or {}
    paths = data.get("paths") or {}
    oneiros = data.get("oneiros") or {}

    return RunConfig(
        name=str(data.get("name") or path.stem),
        description=str(data.get("description") or ""),
        run=BenchmarkRun(
            days=int(run.get("days", 28)),
            seed=int(run.get("seed", 42)),
            scenario=str(run.get("scenario", "default")),
            initial_cash=float(run.get("initial_cash", 1_000_000)),
        ),
        model=ModelConfig(
            provider=str(model.get("provider", "azure_openai")),
            model_label=str(model.get("model_label", "gpt-5")),
            deployment=str(model.get("deployment", "")),
            reasoning_effort=str(model.get("reasoning_effort", "high")),
        ),
        azure_openai=AzureOpenAIConfig(
            endpoint=str(azure.get("endpoint", "")),
            api_key_env=str(azure.get("api_key_env", "AZURE_OPENAI_API_KEY")),
            api_version=str(azure.get("api_version", "")),
        ),
        paths=PathConfig(
            ceobench_repo=_resolve_config_path(base, paths.get("ceobench_repo", "../ceobench-src")),
            oneiros_repo=_resolve_config_path(base, paths.get("oneiros_repo", "../oneiros")),
        ),
        oneiros=OneirosConfig(
            bin=str(oneiros.get("bin", "oneiros")),
            memory_mode=str(oneiros.get("memory_mode", "run_scoped")),
            ingest_hidden_state=bool(oneiros.get("ingest_hidden_state", False)),
        ),
        raw=data,
    )


def _resolve_config_path(base: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()
