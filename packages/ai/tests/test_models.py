from __future__ import annotations

import pytest
from e_ai import get_model, get_models, get_providers, register_faux_provider


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
