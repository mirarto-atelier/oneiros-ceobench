from __future__ import annotations

from pathlib import Path

from oneiros_ceobench.oneiros_config import load_oneiros_azure_settings, shell_exports


def test_load_oneiros_azure_settings_reads_azure_responses(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[extractor]
provider = "azure-responses"

[extractor.azure_responses]
base_url = "https://example.invalid/openai/v1"
deployment = "gpt-test"
api_version = "v1"
api_key = "secret-value"
ca_bundle = "/tmp/example-ca.crt"
""",
        encoding="utf-8",
    )

    settings = load_oneiros_azure_settings(cfg)

    assert settings.source_path == cfg.resolve()
    assert settings.provider_section == "azure_responses"
    assert settings.base_url == "https://example.invalid/openai/v1"
    assert settings.deployment == "gpt-test"
    assert settings.api_key_set


def test_shell_exports_redacts_api_key():
    output = shell_exports(
        {"AZURE_OPENAI_API_KEY": "secret-value", "AZURE_OPENAI_ENDPOINT": "https://example.invalid"}
    )

    assert "secret-value" not in output
    assert "AZURE_OPENAI_API_KEY='<set>'" in output
