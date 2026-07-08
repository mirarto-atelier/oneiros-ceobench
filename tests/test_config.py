from __future__ import annotations

from pathlib import Path

from oneiros_ceobench.config import expand_env, load_config


def test_expand_env_supports_defaults(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    assert expand_env("${MISSING_VALUE:-fallback}") == "fallback"


def test_load_config_resolves_repo_paths(tmp_path: Path):
    oneiros_config = tmp_path / "oneiros.toml"
    oneiros_config.write_text(
        """
[extractor]
provider = "azure-responses"

[extractor.azure_responses]
base_url = "https://oneiros.example/openai/v1"
deployment = "gpt-oneiros"
api_version = "v1"
api_key = "secret"
ca_bundle = "/tmp/ca.pem"
""",
        encoding="utf-8",
    )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
name: test-run
run:
  days: 14
model:
  deployment: ""
azure_openai:
  source: oneiros
  oneiros_config: {oneiros_config}
paths:
  ceobench_repo: ../ceobench-src
  oneiros_repo: ../oneiros
""",
        encoding="utf-8",
    )

    loaded = load_config(cfg)

    assert loaded.name == "test-run"
    assert loaded.run.days == 14
    assert loaded.model.provider == "azure_openai"
    assert loaded.model.deployment == "gpt-oneiros"
    assert loaded.azure_openai.endpoint == "https://oneiros.example/openai/v1"
    assert loaded.paths.ceobench_repo == (tmp_path / "../ceobench-src").resolve()
