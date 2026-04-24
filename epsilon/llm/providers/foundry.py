from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal
from urllib.parse import urlparse

from ..event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from ..types import AssistantMessage, Context, ErrorEvent, Model, StreamOptions
from .anthropic import (
    AnthropicEffort,
    AnthropicOptions,
    AnthropicThinkingDisplay,
    _resolve_anthropic_options,
    stream_anthropic,
)
from .azure_openai_responses import (
    AzureOpenAIResponsesOptions,
    _resolve_azure_openai_responses_options,
    build_azure_openai_responses_payload,
    stream_azure_openai_responses,
)
from .shared import create_empty_assistant_message, start_background_task
from .simple_options import coerce_stream_options, stream_options_to_kwargs

FoundryEndpoint = Literal["openai", "anthropic"]
MIN_FOUNDRY_OPENAI_MAX_TOKENS = 16


@dataclass(slots=True)
class FoundryOptions(StreamOptions):
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None
    thinking_enabled: bool | None = None
    thinking_budget_tokens: int | None = None
    effort: AnthropicEffort | None = None
    thinking_display: AnthropicThinkingDisplay | None = None
    interleaved_thinking: bool | None = None
    tool_choice: Literal["auto", "any", "none"] | dict[str, str] | None = None
    foundry_project: str | None = None
    foundry_api_version: str | None = None
    foundry_openai_base_url: str | None = None
    foundry_anthropic_base_url: str | None = None
    foundry_deployment_name: str | None = None
    foundry_endpoint: FoundryEndpoint | None = None


def stream_foundry(
    model: Model,
    context: Context,
    options: FoundryOptions | StreamOptions | None = None,
) -> AssistantMessageEventStream:
    resolved_options = _resolve_foundry_options(model, options)
    stream = create_assistant_message_event_stream()
    start_background_task(_run_foundry(stream, model, context, resolved_options))
    return stream


async def _run_foundry(
    stream: AssistantMessageEventStream,
    model: Model,
    context: Context,
    options: FoundryOptions | None,
) -> None:
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    try:
        inner = _build_foundry_inner_stream(model, context, options)
        async for event in inner:
            _apply_foundry_identity_to_event(event, model)
            stream.push(event)

        result = await inner.result()
        _apply_foundry_identity(result, model)
        stream.end(result)
    except Exception as exc:
        output.stop_reason = "error"
        output.error_message = str(exc)
        stream.push(ErrorEvent(reason="error", error=output))
        stream.end(output)


def _build_foundry_inner_stream(
    model: Model,
    context: Context,
    options: FoundryOptions | None,
) -> AssistantMessageEventStream:
    endpoint = resolve_foundry_endpoint(model, options)
    if endpoint == "anthropic":
        deployment_name = resolve_foundry_deployment_name(model, options)
        foundry_model = replace(
            model,
            id=deployment_name,
            api="foundry",
            provider="foundry",
            base_url=resolve_foundry_anthropic_base_url(model, options),
        )
        anthropic_options = coerce_stream_options(options, AnthropicOptions)
        return stream_anthropic(foundry_model, context, anthropic_options)

    foundry_model = replace(
        model,
        api="foundry",
        provider="foundry",
        base_url=resolve_foundry_openai_base_url(model, options),
    )
    return stream_azure_openai_responses(
        foundry_model,
        context,
        _build_foundry_openai_options(model, options),
    )


def _resolve_foundry_options(
    model: Model,
    options: FoundryOptions | StreamOptions | None,
) -> FoundryOptions | None:
    if options is None:
        return None
    if isinstance(options, FoundryOptions):
        return options
    if type(options) is not StreamOptions:
        return coerce_stream_options(options, FoundryOptions)

    if resolve_foundry_endpoint(model) == "anthropic":
        anthropic_options = _resolve_anthropic_options(model, options)
        return coerce_stream_options(anthropic_options, FoundryOptions)

    openai_options = _resolve_azure_openai_responses_options(model, options)
    foundry_options = coerce_stream_options(openai_options, FoundryOptions)
    if foundry_options is None:
        return None
    foundry_kwargs = stream_options_to_kwargs(foundry_options, FoundryOptions)
    foundry_kwargs["reasoning"] = options.reasoning
    return FoundryOptions(**foundry_kwargs)


def build_foundry_responses_payload(
    model: Model,
    context: Context,
    options: FoundryOptions | StreamOptions | None = None,
) -> dict[str, object]:
    resolved_options = _resolve_foundry_options(model, options)
    if resolve_foundry_endpoint(model, resolved_options) == "anthropic":
        raise ValueError(
            "Foundry Responses payloads are only valid for OpenAI-compatible Foundry models."
        )
    provider_model = replace(
        model,
        id=resolve_foundry_deployment_name(model, resolved_options),
        api="foundry",
        provider="foundry",
        base_url=resolve_foundry_openai_base_url(model, resolved_options),
    )
    payload = build_azure_openai_responses_payload(
        provider_model,
        context,
        _build_foundry_openai_options(model, resolved_options),
    )
    if payload.get("reasoning") == {"effort": "none"}:
        payload.pop("reasoning", None)
        payload.pop("include", None)
    return payload


def _build_foundry_openai_options(
    model: Model,
    options: FoundryOptions | None,
) -> AzureOpenAIResponsesOptions:
    openai_options = coerce_stream_options(options, AzureOpenAIResponsesOptions)
    if openai_options is None:
        openai_options = AzureOpenAIResponsesOptions()

    openai_options.azure_api_version = (
        options.foundry_api_version if options else None
    ) or os.environ.get("FOUNDRY_API_VERSION")
    openai_options.azure_base_url = resolve_foundry_openai_base_url(model, options)
    openai_options.azure_deployment_name = resolve_foundry_deployment_name(model, options)
    _validate_foundry_openai_options(model, openai_options)
    return openai_options


def _validate_foundry_openai_options(
    model: Model,
    options: AzureOpenAIResponsesOptions,
) -> None:
    if (
        options.max_tokens is not None
        and options.max_tokens < MIN_FOUNDRY_OPENAI_MAX_TOKENS
    ):
        minimum = MIN_FOUNDRY_OPENAI_MAX_TOKENS
        raise ValueError(
            f"Foundry OpenAI-compatible models require max_tokens >= {minimum}; "
            f"got {options.max_tokens} for foundry/{model.id}."
        )

    if options.reasoning_effort == "none":
        raise ValueError(
            f"Foundry OpenAI-compatible models do not support reasoning='none'; "
            f"omit reasoning or use one of minimal/low/medium/high for foundry/{model.id}."
        )

    if options.reasoning == "none":
        raise ValueError(
            f"Foundry OpenAI-compatible models do not support reasoning='none'; "
            f"omit reasoning or use one of minimal/low/medium/high for foundry/{model.id}."
        )


def get_foundry_api_key() -> str | None:
    return os.environ.get("FOUNDRY_API_KEY")


def get_foundry_project() -> str | None:
    return _normalize_foundry_project(os.environ.get("FOUNDRY_PROJECT"))


def get_foundry_openai_base_url() -> str | None:
    explicit = _normalize_base_url(os.environ.get("FOUNDRY_OPENAI_BASE_URL"))
    if explicit is not None:
        return explicit

    project = get_foundry_project()
    if project is None:
        return None
    return f"https://{project}.openai.azure.com/openai/v1"


def get_foundry_anthropic_base_url() -> str | None:
    explicit = _normalize_base_url(os.environ.get("FOUNDRY_ANTHROPIC_BASE_URL"))
    if explicit is not None:
        return explicit

    project = get_foundry_project()
    if project is None:
        return None
    return f"https://{project}.services.ai.azure.com/anthropic/v1"


def resolve_foundry_openai_base_url(
    model: Model,
    options: FoundryOptions | None = None,
) -> str:
    explicit = _normalize_base_url(options.foundry_openai_base_url if options else None)
    if explicit is not None:
        return explicit

    project = _resolve_foundry_project(options)
    if project is not None:
        return f"https://{project}.openai.azure.com/openai/v1"

    if model.base_url and not is_foundry_anthropic_base_url(model.base_url):
        return model.base_url.rstrip("/")

    base_url = get_foundry_openai_base_url()
    if base_url is not None:
        return base_url

    raise ValueError(
        "Foundry OpenAI base URL is required. Set FOUNDRY_OPENAI_BASE_URL or FOUNDRY_PROJECT."
    )


def resolve_foundry_anthropic_base_url(
    model: Model,
    options: FoundryOptions | None = None,
) -> str:
    explicit = _normalize_base_url(options.foundry_anthropic_base_url if options else None)
    if explicit is not None:
        return explicit

    project = _resolve_foundry_project(options)
    if project is not None:
        return f"https://{project}.services.ai.azure.com/anthropic/v1"

    if model.base_url and is_foundry_anthropic_base_url(model.base_url):
        return model.base_url.rstrip("/")

    base_url = get_foundry_anthropic_base_url()
    if base_url is not None:
        return base_url

    raise ValueError(
        "Foundry Anthropic base URL is required. Set FOUNDRY_ANTHROPIC_BASE_URL or FOUNDRY_PROJECT."
    )


def parse_foundry_deployment_name_map(value: str | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not value:
        return mapping
    for entry in value.split(","):
        model_id, separator, deployment_name = entry.strip().partition("=")
        if separator:
            mapping[model_id.strip()] = deployment_name.strip()
    return mapping


def resolve_foundry_deployment_name(
    model: Model,
    options: FoundryOptions | None = None,
) -> str:
    if options and options.foundry_deployment_name:
        return options.foundry_deployment_name
    deployment_map = parse_foundry_deployment_name_map(
        os.environ.get("FOUNDRY_DEPLOYMENT_NAME_MAP")
    )
    return deployment_map.get(model.id, model.id)


def resolve_foundry_endpoint(
    model: Model,
    options: FoundryOptions | None = None,
) -> FoundryEndpoint:
    if options and options.foundry_endpoint is not None:
        return options.foundry_endpoint
    if options and options.foundry_anthropic_base_url:
        return "anthropic"
    if options and options.foundry_openai_base_url:
        return "openai"
    if model.base_url and is_foundry_anthropic_base_url(model.base_url):
        return "anthropic"
    if "claude" in model.id.lower():
        return "anthropic"
    return "openai"


def is_foundry_anthropic_base_url(base_url: str) -> bool:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return False
    parsed = urlparse(normalized)
    return ".services.ai.azure.com" in parsed.netloc and parsed.path.startswith("/anthropic")


def _apply_foundry_identity(message: AssistantMessage, model: Model) -> None:
    message.api = model.api
    message.provider = model.provider
    message.model = model.id


def _apply_foundry_identity_to_event(event: object, model: Model) -> None:
    partial = getattr(event, "partial", None)
    if isinstance(partial, AssistantMessage):
        _apply_foundry_identity(partial, model)

    message = getattr(event, "message", None)
    if isinstance(message, AssistantMessage):
        _apply_foundry_identity(message, model)

    error = getattr(event, "error", None)
    if isinstance(error, AssistantMessage):
        _apply_foundry_identity(error, model)


def _normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def _normalize_foundry_project(project: str | None) -> str | None:
    if project is None:
        return None
    normalized = project.strip().strip("/")
    return normalized or None


def _resolve_foundry_project(options: FoundryOptions | None) -> str | None:
    explicit = _normalize_foundry_project(options.foundry_project if options else None)
    if explicit is not None:
        return explicit
    return get_foundry_project()
