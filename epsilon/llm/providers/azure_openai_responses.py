from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

from ..env_api_keys import get_env_api_key
from ..event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from ..models import supports_xhigh
from ..runtime import RequestAbortedError, is_signal_aborted, maybe_await, raise_if_signal_aborted
from ..types import (
    Context,
    DoneEvent,
    ErrorEvent,
    Model,
    StartEvent,
    StreamOptions,
    resolve_reasoning_level,
)
from .openai_responses_shared import (
    OpenAIResponsesStreamOptions,
    convert_responses_messages,
    convert_responses_tools,
    process_openai_responses_event_stream,
)
from .shared import create_empty_assistant_message, start_background_task
from .simple_options import (
    build_base_options,
    clamp_reasoning,
    coerce_stream_options,
    stream_options_to_kwargs,
)
from .sse import iterate_sse_messages

AZURE_TOOL_CALL_PROVIDERS = {
    "openai",
    "codex",
    "openai-codex",
    "opencode",
    "azure-openai-responses",
    "foundry",
}
DEFAULT_AZURE_API_VERSION = "v1"


@dataclass(slots=True)
class AzureOpenAIResponsesOptions(StreamOptions):
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None
    azure_api_version: str | None = None
    azure_resource_name: str | None = None
    azure_base_url: str | None = None
    azure_deployment_name: str | None = None


def stream_azure_openai_responses(
    model: Model,
    context: Context,
    options: AzureOpenAIResponsesOptions | StreamOptions | None = None,
):
    resolved_options = _resolve_azure_openai_responses_options(model, options)
    stream = create_assistant_message_event_stream()
    start_background_task(_run_azure_openai_responses(stream, model, context, resolved_options))
    return stream


async def _run_azure_openai_responses(
    stream: AssistantMessageEventStream,
    model: Model,
    context: Context,
    options: AzureOpenAIResponsesOptions | None,
) -> None:
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    try:
        raise_if_signal_aborted(options.signal if options else None)

        api_key = options.api_key if options else None
        api_key = api_key or get_env_api_key(model.provider)
        if not api_key:
            raise ValueError("Azure OpenAI API key is required")

        base_url, api_version = resolve_azure_config(model, options)
        deployment_name = resolve_deployment_name(model, options)
        provider_model = Model(
            id=deployment_name,
            name=model.name,
            api=model.api,
            provider=model.provider,
            base_url=base_url,
            reasoning=model.reasoning,
            input=list(model.input),
            cost=model.cost,
            context_window=model.context_window,
            max_tokens=model.max_tokens,
            headers=model.headers,
            compat=model.compat,
        )
        payload = build_azure_openai_responses_payload(provider_model, context, options)
        if options and options.on_payload is not None:
            replacement = await maybe_await(options.on_payload(payload, model))
            if replacement is not None:
                payload = cast(dict[str, object], replacement)

        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            **(model.headers or {}),
            **(options.headers if options and options.headers else {}),
        }
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "POST",
                f"{base_url.rstrip('/')}/responses?api-version={api_version}",
                headers=headers,
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            stream.push(StartEvent(partial=output))
            await process_openai_responses_event_stream(
                _iterate_azure_response_events(response, options.signal if options else None),
                output,
                stream,
                model,
                options=OpenAIResponsesStreamOptions(),
            )

        raise_if_signal_aborted(options.signal if options else None)
        if output.stop_reason in {"error", "aborted"}:
            raise RuntimeError("An unknown error occurred")

        stream.push(
            DoneEvent(
                reason=cast(Literal["stop", "length", "toolUse"], output.stop_reason),
                message=output,
            )
        )
        stream.end(output)
    except Exception as exc:
        output.stop_reason = "aborted" if _is_abort_error(exc, options) else "error"
        output.error_message = await _format_azure_openai_error(exc)
        stream.push(
            ErrorEvent(
                reason=cast(Literal["aborted", "error"], output.stop_reason),
                error=output,
            )
        )
        stream.end(output)


def _resolve_azure_openai_responses_options(
    model: Model,
    options: AzureOpenAIResponsesOptions | StreamOptions | None,
) -> AzureOpenAIResponsesOptions | None:
    if options is None:
        return None
    if isinstance(options, AzureOpenAIResponsesOptions):
        return options
    if type(options) is not StreamOptions:
        return coerce_stream_options(options, AzureOpenAIResponsesOptions)

    base = build_base_options(model, options, options.api_key)
    reasoning_effort = resolve_reasoning_level(options.reasoning)
    if reasoning_effort is not None and not supports_xhigh(model):
        reasoning_effort = clamp_reasoning(reasoning_effort)

    return AzureOpenAIResponsesOptions(
        **stream_options_to_kwargs(base, AzureOpenAIResponsesOptions),
        reasoning_effort=reasoning_effort,
    )


def build_azure_openai_responses_payload(
    model: Model,
    context: Context,
    options: AzureOpenAIResponsesOptions | StreamOptions | None = None,
) -> dict[str, object]:
    resolved_options = coerce_stream_options(options, AzureOpenAIResponsesOptions)
    payload: dict[str, object] = {
        "model": model.id,
        "input": convert_responses_messages(model, context, AZURE_TOOL_CALL_PROVIDERS),
        "stream": True,
    }
    if resolved_options and resolved_options.session_id:
        payload["prompt_cache_key"] = resolved_options.session_id
    if resolved_options and resolved_options.max_tokens is not None:
        payload["max_output_tokens"] = resolved_options.max_tokens
    if resolved_options and resolved_options.temperature is not None:
        payload["temperature"] = resolved_options.temperature
    if resolved_options and resolved_options.top_p is not None:
        payload["top_p"] = resolved_options.top_p
    if resolved_options and (
        resolved_options.text_verbosity is not None or resolved_options.text_format is not None
    ):
        text: dict[str, object] = {}
        if resolved_options.text_verbosity is not None:
            text["verbosity"] = resolved_options.text_verbosity
        if resolved_options.text_format is not None:
            text["format"] = resolved_options.text_format
        payload["text"] = text
    if resolved_options and resolved_options.metadata is not None:
        payload["metadata"] = resolved_options.metadata
    if context.tools:
        payload["tools"] = convert_responses_tools(context.tools)
    if model.reasoning:
        if resolved_options and (
            resolved_options.reasoning_effort or resolved_options.reasoning_summary
        ):
            payload["reasoning"] = {
                "effort": resolved_options.reasoning_effort or "medium",
                "summary": resolved_options.reasoning_summary or "auto",
            }
            payload["include"] = ["reasoning.encrypted_content"]
        else:
            payload["reasoning"] = {"effort": "none"}
    return payload


async def _iterate_azure_response_events(
    response: httpx.Response,
    signal: object | None,
) -> AsyncIterator[dict[str, object]]:
    async for _event_name, data in iterate_sse_messages(response, signal):
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            yield cast(dict[str, object], parsed)


def resolve_deployment_name(
    model: Model,
    options: AzureOpenAIResponsesOptions | None = None,
) -> str:
    if options and options.azure_deployment_name:
        return options.azure_deployment_name
    deployment_map = parse_deployment_name_map(os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME_MAP"))
    return deployment_map.get(model.id, model.id)


def parse_deployment_name_map(value: str | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not value:
        return mapping
    for entry in value.split(","):
        model_id, separator, deployment_name = entry.strip().partition("=")
        if separator:
            mapping[model_id.strip()] = deployment_name.strip()
    return mapping


def resolve_azure_config(
    model: Model,
    options: AzureOpenAIResponsesOptions | None = None,
) -> tuple[str, str]:
    api_version = (
        (options.azure_api_version if options else None)
        or os.environ.get("AZURE_OPENAI_API_VERSION")
        or DEFAULT_AZURE_API_VERSION
    )
    base_url = (options.azure_base_url if options else None) or os.environ.get(
        "AZURE_OPENAI_BASE_URL"
    )
    resource_name = (options.azure_resource_name if options else None) or os.environ.get(
        "AZURE_OPENAI_RESOURCE_NAME"
    )

    resolved_base_url = base_url.strip().rstrip("/") if base_url else ""
    if not resolved_base_url and resource_name:
        resolved_base_url = f"https://{resource_name}.openai.azure.com/openai/v1"
    if not resolved_base_url and model.base_url:
        resolved_base_url = model.base_url.rstrip("/")
    if not resolved_base_url:
        raise ValueError(
            "Azure OpenAI base URL is required. Set AZURE_OPENAI_BASE_URL or "
            "AZURE_OPENAI_RESOURCE_NAME."
        )
    return resolved_base_url, api_version


def _is_abort_error(exc: Exception, options: AzureOpenAIResponsesOptions | None) -> bool:
    return isinstance(exc, RequestAbortedError) or is_signal_aborted(
        options.signal if options else None
    )


async def _format_azure_openai_error(exc: Exception) -> str:
    if not isinstance(exc, httpx.HTTPStatusError):
        return str(exc)

    response = exc.response
    detail = await _extract_azure_openai_error_detail(response)
    if detail:
        return f"{exc}. Response body: {detail}"
    return str(exc)


async def _extract_azure_openai_error_detail(response: httpx.Response) -> str | None:
    text = await _read_httpx_response_text(response)
    text = text.strip()
    if not text:
        return None

    try:
        payload = response.json()
    except json.JSONDecodeError:
        return text

    if not isinstance(payload, dict):
        return text

    error = payload.get("error")
    if not isinstance(error, dict):
        return text

    message = error.get("message")
    param = error.get("param")
    code = error.get("code")

    parts: list[str] = []
    if isinstance(message, str) and message:
        parts.append(message)
    if isinstance(param, str) and param:
        parts.append(f"param={param}")
    if isinstance(code, str) and code:
        parts.append(f"code={code}")
    if parts:
        return "; ".join(parts)

    return _compact_json(payload)


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


async def _read_httpx_response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        await response.aread()
        return response.text
