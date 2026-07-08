from __future__ import annotations

from pathlib import Path

from oneiros_ceobench.config import expand_env, load_config


def test_expand_env_supports_defaults(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    assert expand_env("${MISSING_VALUE:-fallback}") == "fallback"


def test_load_config_resolves_repo_paths(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
name: test-run
run:
  days: 14
model:
  deployment: test-deployment
azure_openai:
  endpoint: https://example.invalid
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
    assert loaded.model.deployment == "test-deployment"
    assert loaded.paths.ceobench_repo == (tmp_path / "../ceobench-src").resolve()
