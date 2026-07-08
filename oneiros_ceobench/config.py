from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .oneiros_config import OneirosAzureSettings, load_oneiros_azure_settings

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
    source: str
    endpoint: str
    api_key_env: str
    api_version: str
    ca_bundle: str
    oneiros_config: Path | None
    provider_section: str | None


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
    oneiros_azure: OneirosAzureSettings | None = None


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

    azure_source = str(azure.get("source", "oneiros"))
    oneiros_azure = _load_inherited_oneiros_azure(azure, azure_source)

    endpoint = str(azure.get("endpoint", ""))
    api_version = str(azure.get("api_version", ""))
    ca_bundle = str(azure.get("ca_bundle", ""))
    deployment = str(model.get("deployment", ""))
    if oneiros_azure is not None:
        endpoint = _prefer_config_value(endpoint, oneiros_azure.base_url)
        api_version = _prefer_config_value(api_version, oneiros_azure.api_version)
        ca_bundle = _prefer_config_value(ca_bundle, oneiros_azure.ca_bundle)
        deployment = _prefer_config_value(deployment, oneiros_azure.deployment)

    model_label = str(model.get("model_label", ""))
    model_label = _prefer_config_value(model_label, deployment or "gpt-5")

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
            model_label=model_label,
            deployment=deployment,
            reasoning_effort=str(model.get("reasoning_effort", "high")),
        ),
        azure_openai=AzureOpenAIConfig(
            source=azure_source,
            endpoint=endpoint,
            api_key_env=str(azure.get("api_key_env", "AZURE_OPENAI_API_KEY")),
            api_version=api_version,
            ca_bundle=ca_bundle,
            oneiros_config=_optional_path(azure.get("oneiros_config")),
            provider_section=_optional_string(azure.get("provider_section")),
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
        oneiros_azure=oneiros_azure,
    )


def _resolve_config_path(base: Path, value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _load_inherited_oneiros_azure(
    azure: dict[str, Any],
    source: str,
) -> OneirosAzureSettings | None:
    if source != "oneiros":
        return None
    return load_oneiros_azure_settings(
        config_path=_optional_path(azure.get("oneiros_config")),
        provider_section=_optional_string(azure.get("provider_section")),
    )


def _optional_path(value: Any) -> Path | None:
    if value in (None, "", "auto"):
        return None
    return Path(str(value)).expanduser()


def _optional_string(value: Any) -> str | None:
    if value in (None, "", "auto"):
        return None
    return str(value)


def _prefer_config_value(value: str, fallback: str) -> str:
    if not value or "${" in value:
        return fallback
    return value
