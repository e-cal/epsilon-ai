from __future__ import annotations

from e_ai import get_api_provider, get_model


def test_built_in_api_providers_are_registered() -> None:
    assert get_api_provider("openai-responses") is not None
    assert get_api_provider("anthropic-messages") is not None
    assert get_api_provider("azure-openai-responses") is not None


def test_builtin_models_cover_initial_provider_scope() -> None:
    assert get_model("openai", "gpt-4o-mini").api == "openai-responses"
    assert get_model("anthropic", "claude-sonnet-4-20250514").api == "anthropic-messages"
    assert get_model("azure-openai-responses", "gpt-4o-mini").api == "azure-openai-responses"
