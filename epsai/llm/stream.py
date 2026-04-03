from __future__ import annotations

from .api_registry import get_api_provider
from .providers.register_builtins import register_built_in_api_providers
from .types import AssistantMessage, Context, Model, ProviderStreamOptions, SimpleStreamOptions

register_built_in_api_providers()


def _resolve_api_provider(api: str):
    provider = get_api_provider(api)
    if provider is None:
        raise LookupError(f"No API provider registered for api: {api}")
    return provider


def stream(
    model: Model,
    context: Context,
    options: ProviderStreamOptions | None = None,
):
    provider = _resolve_api_provider(model.api)
    return provider.stream(model, context, options)


async def complete(
    model: Model,
    context: Context,
    options: ProviderStreamOptions | None = None,
) -> AssistantMessage:
    return await stream(model, context, options).result()


def stream_simple(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
):
    provider = _resolve_api_provider(model.api)
    return provider.stream_simple(model, context, options)


async def complete_simple(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
) -> AssistantMessage:
    return await stream_simple(model, context, options).result()
