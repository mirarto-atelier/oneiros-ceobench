from __future__ import annotations

import json
import os
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROVIDER_SECTIONS = {
    "azure-responses": "azure_responses",
    "azure_responses": "azure_responses",
    "azure-completions": "azure_completions",
    "azure_completions": "azure_completions",
}


@dataclass(frozen=True)
class OneirosAzureSettings:
    source_path: Path
    extractor_provider: str
    provider_section: str
    base_url: str
    deployment: str
    api_version: str
    api_key: str
    ca_bundle: str

    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    def public_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "extractor_provider": self.extractor_provider,
            "provider_section": self.provider_section,
            "base_url": self.base_url,
            "deployment": self.deployment,
            "api_version": self.api_version,
            "api_key": "<set>" if self.api_key else "",
            "ca_bundle": self.ca_bundle,
            "ca_bundle_exists": bool(self.ca_bundle and Path(self.ca_bundle).expanduser().exists()),
        }

    def env(self, *, include_secret: bool) -> dict[str, str]:
        env: dict[str, str] = {}
        if self.base_url:
            env["AZURE_OPENAI_ENDPOINT"] = self.base_url
            # Codex and OpenAI-compatible clients usually key off OPENAI_BASE_URL.
            env["OPENAI_BASE_URL"] = self.base_url
        if self.deployment:
            env["AZURE_OPENAI_DEPLOYMENT"] = self.deployment
        if self.api_version:
            env["AZURE_OPENAI_API_VERSION"] = self.api_version
        if self.ca_bundle:
            env["NODE_EXTRA_CA_CERTS"] = self.ca_bundle
            env["REQUESTS_CA_BUNDLE"] = self.ca_bundle
            env["SSL_CERT_FILE"] = self.ca_bundle
        if include_secret and self.api_key:
            env["AZURE_OPENAI_API_KEY"] = self.api_key
            # Some OpenAI-compatible toolchains ignore Azure-specific env names.
            env["OPENAI_API_KEY"] = self.api_key
        return env


def find_oneiros_config(config_path: Path | None = None) -> Path:
    candidates: list[Path] = []
    if config_path is not None:
        candidates.append(config_path.expanduser())
    if os.environ.get("ONEIROS_CONFIG_PATH"):
        candidates.append(Path(os.environ["ONEIROS_CONFIG_PATH"]).expanduser())
    candidates.extend(
        [
            Path.home() / ".oneiros" / "config.toml",
            Path.home() / ".oneiros" / "configs" / "config.toml",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Oneiros config not found. Searched: {searched}")


def load_oneiros_azure_settings(
    config_path: Path | None = None,
    provider_section: str | None = None,
) -> OneirosAzureSettings:
    resolved = find_oneiros_config(config_path)
    cfg = tomllib.loads(resolved.read_text(encoding="utf-8"))
    extractor = _mapping(cfg.get("extractor"))

    extractor_provider = str(extractor.get("provider") or "")
    section_name = provider_section or _PROVIDER_SECTIONS.get(extractor_provider)
    if not section_name:
        known = ", ".join(sorted(_PROVIDER_SECTIONS))
        raise ValueError(
            f"Oneiros extractor.provider={extractor_provider!r} is not an Azure provider. "
            f"Expected one of: {known}."
        )

    azure = _mapping(extractor.get(section_name))
    if not azure:
        raise ValueError(f"Oneiros config has no [extractor.{section_name}] section")

    return OneirosAzureSettings(
        source_path=resolved,
        extractor_provider=extractor_provider,
        provider_section=section_name,
        base_url=str(azure.get("base_url") or azure.get("endpoint") or ""),
        deployment=str(azure.get("deployment") or azure.get("model") or ""),
        api_version=str(azure.get("api_version") or ""),
        api_key=str(azure.get("api_key") or ""),
        ca_bundle=str(azure.get("ca_bundle") or ""),
    )


def shell_exports(env: dict[str, str], *, redact_secrets: bool = True) -> str:
    lines: list[str] = []
    for key in sorted(env):
        value = env[key]
        if redact_secrets and key.endswith(("API_KEY", "TOKEN", "SECRET")):
            value = "<set>" if value else ""
        lines.append(f"export {key}={shlex.quote(value)}")
    return "\n".join(lines)


def json_env(env: dict[str, str], *, redact_secrets: bool = True) -> str:
    payload = {
        key: ("<set>" if redact_secrets and key.endswith(("API_KEY", "TOKEN", "SECRET")) else value)
        for key, value in sorted(env.items())
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
