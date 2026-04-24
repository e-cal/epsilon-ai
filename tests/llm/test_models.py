from __future__ import annotations

import pytest

from epsilon.llm import (
    get_model,
    get_models,
    get_providers,
    register_faux_provider,
    supports_none,
    supports_xhigh,
)


def test_faux_provider_registers_models() -> None:
    registration = register_faux_provider(
        models=[
            {"id": "faux-fast", "name": "Faux Fast", "reasoning": False},
            {"id": "faux-thinker", "name": "Faux Thinker", "reasoning": True},
        ]
    )

    providers = get_providers()
    models = get_models(registration.provider)
    thinker = get_model(registration.provider, "faux-thinker")

    assert registration.provider in providers
    assert [model.id for model in models] == ["faux-fast", "faux-thinker"]
    assert thinker.reasoning is True

    registration.unregister()


def test_unknown_model_raises_lookup_error() -> None:
    with pytest.raises(LookupError):
        get_model("missing", "missing")


def test_supports_none_for_non_reasoning_models() -> None:
    model = get_model("openai", "gpt-4.1")

    assert supports_none(model) is True


def test_supports_none_rejects_gpt_5_mini() -> None:
    model = get_model("openai", "gpt-5-mini")

    assert supports_none(model) is False


def test_supports_xhigh_limits_to_supported_models() -> None:
    gpt_5 = get_model("openai", "gpt-5")
    gpt_52 = get_model("openai", "gpt-5.2")

    assert supports_xhigh(gpt_5) is False
    assert supports_xhigh(gpt_52) is True
