from __future__ import annotations

from copy import deepcopy

from .model_catalog import BUILTIN_MODELS
from .types import Cost, Model, Provider, Usage

_PROVIDER_MODELS: dict[Provider, dict[str, Model]] = {
    provider: {model_id: deepcopy(model) for model_id, model in models.items()}
    for provider, models in BUILTIN_MODELS.items()
}


def register_models(*models: Model) -> None:
    for model in models:
        _PROVIDER_MODELS.setdefault(model.provider, {})[model.id] = model


def unregister_provider_models(provider: Provider) -> None:
    _PROVIDER_MODELS.pop(provider, None)


def clear_models() -> None:
    _PROVIDER_MODELS.clear()


def reset_models() -> None:
    clear_models()
    for provider, models in BUILTIN_MODELS.items():
        _PROVIDER_MODELS[provider] = {
            model_id: deepcopy(model) for model_id, model in models.items()
        }


def get_providers() -> list[Provider]:
    return sorted(_PROVIDER_MODELS)


def get_models(provider: Provider) -> list[Model]:
    return sorted(_PROVIDER_MODELS.get(provider, {}).values(), key=lambda model: model.id)


def get_model(provider: Provider, model_id: str) -> Model:
    try:
        return _PROVIDER_MODELS[provider][model_id]
    except KeyError as exc:
        raise LookupError(f"Unknown model {provider}/{model_id}") from exc


def calculate_cost(model: Model, usage: Usage) -> Cost:
    usage.cost.input = (model.cost.input / 1_000_000) * usage.input
    usage.cost.output = (model.cost.output / 1_000_000) * usage.output
    usage.cost.cache_read = (model.cost.cache_read / 1_000_000) * usage.cache_read
    usage.cost.cache_write = (model.cost.cache_write / 1_000_000) * usage.cache_write
    usage.cost.total = (
        usage.cost.input + usage.cost.output + usage.cost.cache_read + usage.cost.cache_write
    )
    return usage.cost


def supports_xhigh(model: Model) -> bool:
    return any(
        part in model.id for part in ("gpt-5.2", "gpt-5.3", "gpt-5.4", "opus-4-6", "opus-4.6")
    )


def models_are_equal(a: Model | None, b: Model | None) -> bool:
    if a is None or b is None:
        return False
    return a.id == b.id and a.provider == b.provider
