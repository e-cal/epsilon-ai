from __future__ import annotations

from dataclasses import dataclass

from .types import Api, Context, Model, StreamFunction, StreamOptions


@dataclass(slots=True)
class ApiProvider:
    api: Api
    stream: StreamFunction


_API_PROVIDERS: dict[Api, ApiProvider] = {}


def _wrap_stream(api: Api, stream: StreamFunction) -> StreamFunction:
    def wrapped(
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ):
        if model.api != api:
            raise ValueError(f"Mismatched api: {model.api} expected {api}")
        return stream(model, context, options)

    return wrapped


def register_api_provider(provider: ApiProvider) -> None:
    _API_PROVIDERS[provider.api] = ApiProvider(
        api=provider.api,
        stream=_wrap_stream(provider.api, provider.stream),
    )


def unregister_api_provider(api: Api) -> None:
    _API_PROVIDERS.pop(api, None)


def clear_api_providers() -> None:
    _API_PROVIDERS.clear()


def get_api_provider(api: Api) -> ApiProvider | None:
    return _API_PROVIDERS.get(api)


def get_api_providers() -> list[ApiProvider]:
    return list(_API_PROVIDERS.values())
