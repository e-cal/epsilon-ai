from __future__ import annotations

import asyncio

from .api_registry import get_api_provider
from .providers.register_builtins import register_built_in_api_providers
from .types import AssistantMessage, Context, Model, StreamOptions

register_built_in_api_providers()


def _resolve_api_provider(api: str):
    provider = get_api_provider(api)
    if provider is None:
        raise LookupError(f"No API provider registered for api: {api}")
    return provider


def stream(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
):
    provider = _resolve_api_provider(model.api)
    return provider.stream(model, context, options)


def complete(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AssistantMessage:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(complete_async(model, context, options))
    raise RuntimeError(
        "epsilon.llm.complete() is synchronous; "
        "use await epsilon.llm.complete_async(...) in async code"
    )


async def complete_async(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AssistantMessage:
    return await stream(model, context, options).result()
