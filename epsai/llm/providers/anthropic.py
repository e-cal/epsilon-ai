from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, cast

import httpx

from ..env_api_keys import get_env_api_key
from ..event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from ..json_parse import parse_streaming_json
from ..models import calculate_cost
from ..runtime import RequestAbortedError, is_signal_aborted, maybe_await, raise_if_signal_aborted
from ..sanitize_unicode import sanitize_surrogates
from ..types import (
    AssistantMessage,
    CacheRetention,
    Context,
    DoneEvent,
    ErrorEvent,
    ImageContent,
    JSONObject,
    Message,
    Model,
    SimpleStreamOptions,
    StartEvent,
    StopReason,
    StreamOptions,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingContent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingLevel,
    ThinkingStartEvent,
    Tool,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultMessage,
)
from .shared import create_empty_assistant_message, start_background_task
from .simple_options import adjust_max_tokens_for_thinking, build_base_options
from .sse import iterate_sse_messages
from .transform_messages import transform_messages

AnthropicEffort = Literal["low", "medium", "high", "max"]
CLAUDE_CODE_VERSION = "2.1.75"
CLAUDE_CODE_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Grep",
    "Glob",
    "AskUserQuestion",
    "EnterPlanMode",
    "ExitPlanMode",
    "KillShell",
    "NotebookEdit",
    "Skill",
    "Task",
    "TaskOutput",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
]
CLAUDE_CODE_TOOL_LOOKUP = {tool.lower(): tool for tool in CLAUDE_CODE_TOOLS}


@dataclass(slots=True)
class AnthropicOptions(StreamOptions):
    thinking_enabled: bool | None = None
    thinking_budget_tokens: int | None = None
    effort: AnthropicEffort | None = None
    interleaved_thinking: bool | None = None
    tool_choice: Literal["auto", "any", "none"] | dict[str, str] | None = None


def stream_anthropic(
    model: Model,
    context: Context,
    options: AnthropicOptions | None = None,
):
    stream = create_assistant_message_event_stream()
    start_background_task(_run_anthropic(stream, model, context, options))
    return stream


async def _run_anthropic(
    stream: AssistantMessageEventStream,
    model: Model,
    context: Context,
    options: AnthropicOptions | None,
) -> None:
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    try:
        raise_if_signal_aborted(options.signal if options else None)

        api_key = options.api_key if options else None
        api_key = api_key or get_env_api_key(model.provider)
        if not api_key:
            raise ValueError("Anthropic API key is required")

        is_oauth = is_oauth_token(api_key)
        payload = build_anthropic_payload(model, context, options, is_oauth)
        if options and options.on_payload is not None:
            replacement = await maybe_await(options.on_payload(payload, model))
            if replacement is not None:
                payload = cast(dict[str, object], replacement)

        headers = build_anthropic_headers(model, api_key, options, is_oauth)
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "POST",
                anthropic_messages_url(model.base_url),
                headers=headers,
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            stream.push(StartEvent(partial=output))
            await process_anthropic_event_stream(
                _iterate_anthropic_events(response, options.signal if options else None),
                output,
                stream,
                model,
                context.tools,
                is_oauth,
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
        output.error_message = str(exc)
        stream.push(
            ErrorEvent(
                reason=cast(Literal["aborted", "error"], output.stop_reason),
                error=output,
            )
        )
        stream.end(output)


def stream_simple_anthropic(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
):
    api_key = options.api_key if options else None
    api_key = api_key or get_env_api_key(model.provider)
    if not api_key:
        raise ValueError(f"No API key for provider: {model.provider}")

    base = build_base_options(model, options, api_key)
    if not options or not options.reasoning:
        return stream_anthropic(
            model, context, AnthropicOptions(**base.__dict__, thinking_enabled=False)
        )

    if supports_adaptive_thinking(model.id):
        return stream_anthropic(
            model,
            context,
            AnthropicOptions(
                **base.__dict__,
                thinking_enabled=True,
                effort=map_thinking_level_to_effort(options.reasoning, model.id),
            ),
        )

    max_tokens, thinking_budget = adjust_max_tokens_for_thinking(
        base.max_tokens or 0,
        model.max_tokens,
        options.reasoning,
        options.thinking_budgets,
    )
    return stream_anthropic(
        model,
        context,
        AnthropicOptions(
            **base.__dict__,
            max_tokens=max_tokens,
            thinking_enabled=True,
            thinking_budget_tokens=thinking_budget,
        ),
    )


def build_anthropic_payload(
    model: Model,
    context: Context,
    options: AnthropicOptions | None = None,
    is_oauth_token_value: bool = False,
) -> dict[str, object]:
    cache_control = get_cache_control(model.base_url, options.cache_retention if options else None)
    payload: dict[str, object] = {
        "model": model.id,
        "messages": convert_anthropic_messages(
            context.messages,
            model,
            is_oauth_token_value,
            cache_control,
        ),
        "max_tokens": (
            options.max_tokens if options and options.max_tokens else model.max_tokens // 3
        ),
        "stream": True,
    }

    if is_oauth_token_value:
        system_blocks: list[dict[str, object]] = [
            {
                "type": "text",
                "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                **({"cache_control": cache_control} if cache_control else {}),
            }
        ]
        if context.system_prompt:
            system_blocks.append(
                {
                    "type": "text",
                    "text": sanitize_surrogates(context.system_prompt),
                    **({"cache_control": cache_control} if cache_control else {}),
                }
            )
        payload["system"] = system_blocks
    elif context.system_prompt:
        payload["system"] = [
            {
                "type": "text",
                "text": sanitize_surrogates(context.system_prompt),
                **({"cache_control": cache_control} if cache_control else {}),
            }
        ]

    if options and options.temperature is not None and not options.thinking_enabled:
        payload["temperature"] = options.temperature
    if context.tools:
        payload["tools"] = convert_anthropic_tools(context.tools, is_oauth_token_value)
    if model.reasoning:
        if options and options.thinking_enabled:
            if supports_adaptive_thinking(model.id):
                payload["thinking"] = {"type": "adaptive"}
                if options.effort is not None:
                    payload["output_config"] = {"effort": options.effort}
            else:
                payload["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": options.thinking_budget_tokens or 1024,
                }
        elif options and options.thinking_enabled is False:
            payload["thinking"] = {"type": "disabled"}
    if options and options.metadata:
        user_id = options.metadata.get("user_id")
        if isinstance(user_id, str):
            payload["metadata"] = {"user_id": user_id}
    if options and options.tool_choice is not None:
        payload["tool_choice"] = (
            {"type": options.tool_choice}
            if isinstance(options.tool_choice, str)
            else options.tool_choice
        )
    return payload


def convert_anthropic_messages(
    messages: list[Message],
    model: Model,
    is_oauth_token_value: bool,
    cache_control: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    params: list[dict[str, object]] = []
    transformed = transform_messages(messages, model, normalize_anthropic_tool_call_id)

    index = 0
    while index < len(transformed):
        message = transformed[index]
        if message.role == "user":
            if isinstance(message.content, str):
                if message.content.strip():
                    params.append(
                        {
                            "role": "user",
                            "content": sanitize_surrogates(message.content),
                        }
                    )
            else:
                blocks: list[dict[str, object]] = []
                for block in message.content:
                    if block.type == "text":
                        if block.text.strip():
                            blocks.append({"type": "text", "text": sanitize_surrogates(block.text)})
                    elif "image" in model.input:
                        blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": block.mime_type,
                                    "data": block.data,
                                },
                            }
                        )
                if blocks:
                    params.append({"role": "user", "content": blocks})
            index += 1
            continue

        if message.role == "assistant":
            blocks: list[dict[str, object]] = []
            for block in message.content:
                if block.type == "text":
                    if block.text.strip():
                        blocks.append({"type": "text", "text": sanitize_surrogates(block.text)})
                    continue

                if block.type == "thinking":
                    if block.redacted:
                        blocks.append(
                            {
                                "type": "redacted_thinking",
                                "data": block.thinking_signature or "",
                            }
                        )
                        continue
                    if not block.thinking.strip():
                        continue
                    if not block.thinking_signature or not block.thinking_signature.strip():
                        blocks.append({"type": "text", "text": sanitize_surrogates(block.thinking)})
                    else:
                        blocks.append(
                            {
                                "type": "thinking",
                                "thinking": sanitize_surrogates(block.thinking),
                                "signature": block.thinking_signature,
                            }
                        )
                    continue

                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": to_claude_code_name(block.name)
                        if is_oauth_token_value
                        else block.name,
                        "input": block.arguments,
                    }
                )

            if blocks:
                params.append({"role": "assistant", "content": blocks})
            index += 1
            continue

        tool_results: list[dict[str, object]] = []
        while index < len(transformed) and transformed[index].role == "toolResult":
            tool_result = cast(ToolResultMessage, transformed[index])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_result.tool_call_id,
                    "content": convert_content_blocks(tool_result.content),
                    "is_error": tool_result.is_error,
                }
            )
            index += 1
        params.append({"role": "user", "content": tool_results})

    if cache_control and params:
        last_message = params[-1]
        if last_message.get("role") == "user":
            content = last_message.get("content")
            if isinstance(content, str):
                last_message["content"] = [
                    {"type": "text", "text": content, "cache_control": cache_control}
                ]
            elif isinstance(content, list) and content:
                last_block = content[-1]
                if isinstance(last_block, dict) and last_block.get("type") in {
                    "text",
                    "image",
                    "tool_result",
                }:
                    last_block["cache_control"] = cache_control

    return params


def convert_anthropic_tools(
    tools: list[Tool], is_oauth_token_value: bool
) -> list[dict[str, object]]:
    return [
        {
            "name": to_claude_code_name(tool.name) if is_oauth_token_value else tool.name,
            "description": tool.description,
            "input_schema": {
                "type": "object",
                "properties": tool.parameters.get("properties", {}),
                "required": tool.parameters.get("required", []),
            },
        }
        for tool in tools
    ]


async def process_anthropic_event_stream(
    events: AsyncIterator[dict[str, object]],
    output: AssistantMessage,
    stream: AssistantMessageEventStream,
    model: Model,
    tools: list[Tool] | None,
    is_oauth_token_value: bool,
) -> None:
    content_index_by_event_index: dict[int, int] = {}
    tool_json_by_event_index: dict[int, str] = {}

    assistant = output

    async for event in events:
        event_type = cast(str | None, event.get("type"))
        if event_type == "ping":
            continue

        if event_type == "message_start":
            message = cast(dict[str, object], event.get("message") or {})
            usage = cast(dict[str, object], message.get("usage") or {})
            assistant.response_id = cast(str | None, message.get("id"))
            assistant.usage.input = _int_value(usage.get("input_tokens"), 0)
            assistant.usage.output = _int_value(usage.get("output_tokens"), 0)
            assistant.usage.cache_read = _int_value(usage.get("cache_read_input_tokens"), 0)
            assistant.usage.cache_write = _int_value(usage.get("cache_creation_input_tokens"), 0)
            assistant.usage.total_tokens = (
                assistant.usage.input
                + assistant.usage.output
                + assistant.usage.cache_read
                + assistant.usage.cache_write
            )
            calculate_cost(model, assistant.usage)
            continue

        if event_type == "content_block_start":
            event_index = _int_value(event.get("index"), 0)
            content_block = cast(dict[str, object], event.get("content_block") or {})
            block_type = content_block.get("type")
            if block_type == "text":
                assistant.content.append(TextContent(text=""))
                content_index_by_event_index[event_index] = len(assistant.content) - 1
                stream.push(
                    TextStartEvent(content_index=len(assistant.content) - 1, partial=assistant)
                )
            elif block_type == "thinking":
                assistant.content.append(ThinkingContent(thinking="", thinking_signature=""))
                content_index_by_event_index[event_index] = len(assistant.content) - 1
                stream.push(
                    ThinkingStartEvent(content_index=len(assistant.content) - 1, partial=assistant)
                )
            elif block_type == "redacted_thinking":
                assistant.content.append(
                    ThinkingContent(
                        thinking="[Reasoning redacted]",
                        thinking_signature=cast(str | None, content_block.get("data")),
                        redacted=True,
                    )
                )
                content_index_by_event_index[event_index] = len(assistant.content) - 1
                stream.push(
                    ThinkingStartEvent(content_index=len(assistant.content) - 1, partial=assistant)
                )
            elif block_type == "tool_use":
                tool_name = cast(str, content_block.get("name") or "")
                assistant.content.append(
                    ToolCall(
                        id=cast(str, content_block.get("id") or ""),
                        name=from_claude_code_name(tool_name, tools)
                        if is_oauth_token_value
                        else tool_name,
                        arguments=cast(JSONObject, content_block.get("input") or {}),
                    )
                )
                content_index_by_event_index[event_index] = len(assistant.content) - 1
                tool_json_by_event_index[event_index] = ""
                stream.push(
                    ToolCallStartEvent(content_index=len(assistant.content) - 1, partial=assistant)
                )
            continue

        if event_type == "content_block_delta":
            event_index = _int_value(event.get("index"), 0)
            content_index = content_index_by_event_index.get(event_index)
            if content_index is None:
                continue
            block = assistant.content[content_index]
            delta = cast(dict[str, object], event.get("delta") or {})
            delta_type = delta.get("type")
            if delta_type == "text_delta" and isinstance(block, TextContent):
                text_delta = cast(str, delta.get("text") or "")
                block.text += text_delta
                stream.push(
                    TextDeltaEvent(content_index=content_index, delta=text_delta, partial=assistant)
                )
            elif delta_type == "thinking_delta" and isinstance(block, ThinkingContent):
                thinking_delta = cast(str, delta.get("thinking") or "")
                block.thinking += thinking_delta
                stream.push(
                    ThinkingDeltaEvent(
                        content_index=content_index,
                        delta=thinking_delta,
                        partial=assistant,
                    )
                )
            elif delta_type == "input_json_delta" and isinstance(block, ToolCall):
                partial_json = cast(str, delta.get("partial_json") or "")
                tool_json_by_event_index[event_index] = (
                    tool_json_by_event_index.get(event_index, "") + partial_json
                )
                block.arguments = parse_streaming_json(tool_json_by_event_index[event_index])
                stream.push(
                    ToolCallDeltaEvent(
                        content_index=content_index,
                        delta=partial_json,
                        partial=assistant,
                    )
                )
            elif delta_type == "signature_delta" and isinstance(block, ThinkingContent):
                block.thinking_signature = (block.thinking_signature or "") + cast(
                    str,
                    delta.get("signature") or "",
                )
            continue

        if event_type == "content_block_stop":
            event_index = _int_value(event.get("index"), 0)
            content_index = content_index_by_event_index.pop(event_index, None)
            if content_index is None:
                continue
            block = assistant.content[content_index]
            if isinstance(block, TextContent):
                stream.push(
                    TextEndEvent(content_index=content_index, content=block.text, partial=assistant)
                )
            elif isinstance(block, ThinkingContent):
                stream.push(
                    ThinkingEndEvent(
                        content_index=content_index,
                        content=block.thinking,
                        partial=assistant,
                    )
                )
            elif isinstance(block, ToolCall):
                partial_json = tool_json_by_event_index.pop(event_index, "")
                if partial_json:
                    block.arguments = parse_streaming_json(partial_json)
                stream.push(
                    ToolCallEndEvent(
                        content_index=content_index, tool_call=block, partial=assistant
                    )
                )
            continue

        if event_type == "message_delta":
            delta = cast(dict[str, object], event.get("delta") or {})
            usage = cast(dict[str, object], event.get("usage") or {})
            stop_reason = delta.get("stop_reason")
            if isinstance(stop_reason, str):
                assistant.stop_reason = map_anthropic_stop_reason(stop_reason)
            if usage.get("input_tokens") is not None:
                assistant.usage.input = _int_value(usage["input_tokens"], 0)
            if usage.get("output_tokens") is not None:
                assistant.usage.output = _int_value(usage["output_tokens"], 0)
            if usage.get("cache_read_input_tokens") is not None:
                assistant.usage.cache_read = _int_value(usage["cache_read_input_tokens"], 0)
            if usage.get("cache_creation_input_tokens") is not None:
                assistant.usage.cache_write = _int_value(usage["cache_creation_input_tokens"], 0)
            assistant.usage.total_tokens = (
                assistant.usage.input
                + assistant.usage.output
                + assistant.usage.cache_read
                + assistant.usage.cache_write
            )
            calculate_cost(model, assistant.usage)
            continue

        if event_type == "error":
            error = event.get("error")
            if isinstance(error, dict):
                raise RuntimeError(cast(str, error.get("message") or "Unknown error"))
            raise RuntimeError(cast(str, error or "Unknown error"))


def resolve_cache_retention(cache_retention: CacheRetention | None) -> CacheRetention:
    if cache_retention is not None:
        return cache_retention
    if os.environ.get("PI_CACHE_RETENTION") == "long":
        return "long"
    return "short"


def get_cache_control(
    base_url: str, cache_retention: CacheRetention | None
) -> dict[str, str] | None:
    retention = resolve_cache_retention(cache_retention)
    if retention == "none":
        return None
    if retention == "long" and "api.anthropic.com" in base_url:
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def convert_content_blocks(
    content: list[TextContent | ImageContent],
) -> str | list[dict[str, object]]:
    has_images = any(getattr(block, "type", None) == "image" for block in content)
    if not has_images:
        return sanitize_surrogates(
            "\n".join(
                cast(TextContent, block).text
                for block in content
                if getattr(block, "type", None) == "text"
            )
        )

    blocks: list[dict[str, object]] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            text_block = cast(TextContent, block)
            blocks.append({"type": "text", "text": sanitize_surrogates(text_block.text)})
        else:
            image_block = cast(ImageContent, block)
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_block.mime_type,
                        "data": image_block.data,
                    },
                }
            )

    if not any(block["type"] == "text" for block in blocks):
        blocks.insert(0, {"type": "text", "text": "(see attached image)"})
    return blocks


def build_anthropic_headers(
    model: Model,
    api_key: str,
    options: AnthropicOptions | None,
    is_oauth_token_value: bool,
) -> dict[str, str]:
    needs_interleaved_beta = bool(
        options and options.interleaved_thinking is not False
    ) and not supports_adaptive_thinking(model.id)
    beta_features = ["fine-grained-tool-streaming-2025-05-14"]
    if needs_interleaved_beta:
        beta_features.append("interleaved-thinking-2025-05-14")

    headers = {
        "accept": "application/json",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        **(model.headers or {}),
        **(options.headers if options and options.headers else {}),
    }
    if is_oauth_token_value:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["anthropic-dangerous-direct-browser-access"] = "true"
        headers["anthropic-beta"] = (
            f"claude-code-20250219,oauth-2025-04-20,{','.join(beta_features)}"
        )
        headers["user-agent"] = f"claude-cli/{CLAUDE_CODE_VERSION}"
        headers["x-app"] = "cli"
        return headers

    headers["x-api-key"] = api_key
    headers["anthropic-dangerous-direct-browser-access"] = "true"
    headers["anthropic-beta"] = ",".join(beta_features)
    return headers


def anthropic_messages_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/messages"
    return f"{normalized}/v1/messages"


async def _iterate_anthropic_events(
    response: httpx.Response,
    signal: object | None,
) -> AsyncIterator[dict[str, object]]:
    async for event_name, data in iterate_sse_messages(response, signal):
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            continue
        if event_name and "type" not in parsed:
            parsed["type"] = event_name
        yield cast(dict[str, object], parsed)


def supports_adaptive_thinking(model_id: str) -> bool:
    return any(part in model_id for part in ("opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6"))


def map_thinking_level_to_effort(level: ThinkingLevel, model_id: str) -> AnthropicEffort:
    if level in {"minimal", "low"}:
        return "low"
    if level == "medium":
        return "medium"
    if level == "xhigh" and any(part in model_id for part in ("opus-4-6", "opus-4.6")):
        return "max"
    return "high"


def normalize_anthropic_tool_call_id(
    tool_call_id: str,
    model: Model,
    source: AssistantMessage,
) -> str:
    del model, source
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in tool_call_id)[
        :64
    ]


def to_claude_code_name(name: str) -> str:
    return CLAUDE_CODE_TOOL_LOOKUP.get(name.lower(), name)


def from_claude_code_name(name: str, tools: list[Tool] | None) -> str:
    if tools:
        lower_name = name.lower()
        for tool in tools:
            if tool.name.lower() == lower_name:
                return tool.name
    return name


def is_oauth_token(api_key: str) -> bool:
    return "sk-ant-oat" in api_key


def map_anthropic_stop_reason(reason: str | None) -> StopReason:
    if reason in {None, "end_turn", "pause_turn", "stop_sequence"}:
        return "stop"
    if reason == "max_tokens":
        return "length"
    if reason == "tool_use":
        return "toolUse"
    if reason in {"refusal", "sensitive"}:
        return "error"
    raise ValueError(f"Unhandled Anthropic stop reason: {reason}")


def _is_abort_error(exc: Exception, options: AnthropicOptions | None) -> bool:
    return isinstance(exc, RequestAbortedError) or is_signal_aborted(
        options.signal if options else None
    )


def _int_value(value: object, default: int) -> int:
    return int(value) if isinstance(value, int | float | str) else default
