from __future__ import annotations

from dataclasses import replace

from epsilon.llm.env_api_keys import get_env_api_key
from epsilon.llm.models import get_model
from epsilon.llm.providers.anthropic import build_anthropic_headers
from epsilon.llm.providers.foundry import (
    get_foundry_anthropic_base_url,
    get_foundry_api_key,
    get_foundry_openai_base_url,
    resolve_foundry_anthropic_base_url,
    resolve_foundry_openai_base_url,
)


def _clear_foundry_env(monkeypatch) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_OAUTH_TOKEN",
        "FOUNDRY_ANTHROPIC_BASE_URL",
        "FOUNDRY_API_KEY",
        "FOUNDRY_DEPLOYMENT_NAME_MAP",
        "FOUNDRY_OPENAI_BASE_URL",
        "FOUNDRY_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_foundry_base_urls_derive_from_project(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")

    assert get_foundry_openai_base_url() == "https://epsilon-foundry.openai.azure.com/openai/v1"
    assert (
        get_foundry_anthropic_base_url()
        == "https://epsilon-foundry.services.ai.azure.com/anthropic/v1"
    )


def test_env_api_key_uses_foundry_provider_key(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    monkeypatch.setenv("FOUNDRY_API_KEY", "foundry-key")

    assert get_foundry_api_key() == "foundry-key"
    assert get_env_api_key("foundry") == "foundry-key"


def test_resolve_foundry_openai_base_url_uses_project(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "gpt-4o-mini")

    assert (
        resolve_foundry_openai_base_url(model)
        == "https://epsilon-foundry.openai.azure.com/openai/v1"
    )


def test_resolve_foundry_anthropic_base_url_uses_project(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "claude-sonnet-4-6")

    assert resolve_foundry_anthropic_base_url(model) == (
        "https://epsilon-foundry.services.ai.azure.com/anthropic/v1"
    )


def test_direct_anthropic_model_base_url_does_not_use_foundry_project(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("anthropic", "claude-sonnet-4-6")

    assert model.base_url == "https://api.anthropic.com"


def test_foundry_anthropic_headers_keep_x_api_key(monkeypatch) -> None:
    _clear_foundry_env(monkeypatch)
    model = replace(
        get_model("foundry", "claude-sonnet-4-6"),
        base_url="https://epsilon-foundry.services.ai.azure.com/anthropic/v1",
    )

    headers = build_anthropic_headers(model, "foundry-key", None, False)

    assert headers["x-api-key"] == "foundry-key"
