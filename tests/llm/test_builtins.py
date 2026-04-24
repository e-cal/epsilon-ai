from __future__ import annotations

from epsilon.llm import get_api_provider, get_model


def test_built_in_api_providers_are_registered() -> None:
    assert get_api_provider("openai-responses") is not None
    assert get_api_provider("openai-codex-responses") is not None
    assert get_api_provider("anthropic-messages") is not None
    assert get_api_provider("foundry") is not None


def test_builtin_models_cover_initial_provider_scope() -> None:
    assert get_model("openai", "gpt-4o-mini").api == "openai-responses"
    assert get_model("openai-codex", "gpt-5.3-codex").api == "openai-codex-responses"
    assert get_model("openai-codex", "gpt-5.3-codex").provider == "openai-codex"
    assert get_model("anthropic", "claude-sonnet-4-20250514").api == "anthropic-messages"
    assert get_model("foundry", "gpt-4o-mini").api == "foundry"
    assert get_model("foundry", "claude-sonnet-4-20250514").api == "foundry"
