from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from ..event_stream import AssistantMessageEventStream
from ..hash_utils import short_hash
from ..json_parse import parse_streaming_json
from ..models import calculate_cost
from ..sanitize_unicode import sanitize_surrogates
from ..types import (
    AssistantMessage,
    Context,
    ImageContent,
    Model,
    StopReason,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingContent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    Tool,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    Usage,
)
from .transform_messages import transform_messages

TextPhase = Literal["commentary", "final_answer"]


@dataclass(slots=True)
class OpenAIResponsesStreamOptions:
    service_tier: str | None = None
    apply_service_tier_pricing: Callable[[Usage, str | None], None] | None = None


def convert_responses_messages(
    model: Model,
    context: Context,
    allowed_tool_call_providers: set[str],
    *,
    include_system_prompt: bool = True,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    def normalize_tool_call_id(
        tool_call_id: str,
        _target_model: Model,
        source: AssistantMessage,
    ) -> str:
        if model.provider not in allowed_tool_call_providers:
            return _normalize_id_part(tool_call_id)
        if "|" not in tool_call_id:
            return _normalize_id_part(tool_call_id)

        call_id, item_id = tool_call_id.split("|", 1)
        normalized_call_id = _normalize_id_part(call_id)
        is_foreign_tool_call = source.provider != model.provider or source.api != model.api
        normalized_item_id = (
            _build_foreign_responses_item_id(item_id)
            if is_foreign_tool_call
            else _normalize_id_part(item_id)
        )
        if not normalized_item_id.startswith("fc_"):
            normalized_item_id = _normalize_id_part(f"fc_{normalized_item_id}")
        return f"{normalized_call_id}|{normalized_item_id}"

    transformed_messages = transform_messages(context.messages, model, normalize_tool_call_id)

    if include_system_prompt and context.system_prompt:
        messages.append(
            {
                "role": "developer" if model.reasoning else "system",
                "content": sanitize_surrogates(context.system_prompt),
            }
        )

    for index, message in enumerate(transformed_messages):
        if message.role == "user":
            if isinstance(message.content, str):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": sanitize_surrogates(message.content),
                            }
                        ],
                    }
                )
                continue

            content: list[dict[str, Any]] = []
            for user_block in message.content:
                if isinstance(user_block, TextContent):
                    content.append(
                        {
                            "type": "input_text",
                            "text": sanitize_surrogates(user_block.text),
                        }
                    )
                elif "image" in model.input:
                    image_block = cast(ImageContent, user_block)
                    content.append(
                        {
                            "type": "input_image",
                            "detail": "auto",
                            "image_url": f"data:{image_block.mime_type};base64,{image_block.data}",
                        }
                    )
            if content:
                messages.append({"role": "user", "content": content})
            continue

        if message.role == "assistant":
            assistant_output: list[dict[str, Any]] = []
            is_different_model = (
                message.model != model.id
                and message.provider == model.provider
                and message.api == model.api
            )

            for block in message.content:
                if block.type == "thinking":
                    if not block.thinking_signature:
                        continue
                    try:
                        assistant_output.append(
                            cast(dict[str, Any], json.loads(block.thinking_signature))
                        )
                    except json.JSONDecodeError:
                        continue
                    continue

                if block.type == "text":
                    parsed_signature = _parse_text_signature(block.text_signature)
                    message_id = parsed_signature[0] if parsed_signature else None
                    if not message_id:
                        message_id = f"msg_{index}"
                    elif len(message_id) > 64:
                        message_id = f"msg_{short_hash(message_id)}"

                    item: dict[str, Any] = {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": sanitize_surrogates(block.text),
                                "annotations": [],
                            }
                        ],
                        "status": "completed",
                        "id": message_id,
                    }
                    if parsed_signature and parsed_signature[1] is not None:
                        item["phase"] = parsed_signature[1]
                    assistant_output.append(item)
                    continue

                call_id, separator, item_id_raw = block.id.partition("|")
                item_id = item_id_raw if separator else None
                if is_different_model and item_id and item_id.startswith("fc_"):
                    item_id = None
                assistant_output.append(
                    {
                        "type": "function_call",
                        "id": item_id,
                        "call_id": call_id,
                        "name": block.name,
                        "arguments": json.dumps(block.arguments),
                    }
                )

            if assistant_output:
                messages.extend(assistant_output)
            continue

        text_result = "\n".join(
            sanitize_surrogates(block.text) for block in message.content if block.type == "text"
        )
        image_blocks = [block for block in message.content if isinstance(block, ImageContent)]
        tool_output: str | list[dict[str, Any]]
        if image_blocks and "image" in model.input:
            tool_output = []
            if text_result:
                tool_output.append({"type": "input_text", "text": text_result})
            for block in image_blocks:
                tool_output.append(
                    {
                        "type": "input_image",
                        "detail": "auto",
                        "image_url": f"data:{block.mime_type};base64,{block.data}",
                    }
                )
        else:
            tool_output = text_result or "(see attached image)"

        call_id, _separator, _item_id = message.tool_call_id.partition("|")
        messages.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": tool_output,
            }
        )

    return messages


def convert_responses_tools(
    tools: list[Tool],
    *,
    strict: bool | None = False,
) -> list[dict[str, Any]]:
    strict_mode = False if strict is None else strict
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": strict_mode,
        }
        for tool in tools
    ]


async def process_openai_responses_event_stream(
    events: AsyncIterator[dict[str, Any]],
    output: AssistantMessage,
    stream: AssistantMessageEventStream,
    model: Model,
    *,
    options: OpenAIResponsesStreamOptions | None = None,
) -> None:
    current_item: dict[str, Any] | None = None
    current_block: TextContent | ThinkingContent | ToolCall | None = None
    current_tool_partial_json = ""

    async for event in events:
        event_type = cast(str | None, event.get("type"))
        if event_type == "response.created":
            response = cast(dict[str, Any], event.get("response") or {})
            output.response_id = cast(str | None, response.get("id"))
            continue

        if event_type == "response.output_item.added":
            item = cast(dict[str, Any], event.get("item") or {})
            item_type = item.get("type")
            current_item = item
            if item_type == "reasoning":
                current_block = ThinkingContent(thinking="")
                output.content.append(current_block)
                stream.push(
                    ThinkingStartEvent(content_index=len(output.content) - 1, partial=output)
                )
            elif item_type == "message":
                current_block = TextContent(text="")
                output.content.append(current_block)
                content_index = len(output.content) - 1
                stream.push(TextStartEvent(content_index=content_index, partial=output))
            elif item_type == "function_call":
                current_tool_partial_json = cast(str, item.get("arguments") or "")
                current_block = ToolCall(
                    id=f"{item.get('call_id', '')}|{item.get('id', '')}".rstrip("|"),
                    name=cast(str, item.get("name") or ""),
                    arguments=parse_streaming_json(current_tool_partial_json),
                )
                output.content.append(current_block)
                content_index = len(output.content) - 1
                stream.push(ToolCallStartEvent(content_index=content_index, partial=output))
            continue

        if event_type == "response.reasoning_summary_part.added":
            if current_item and current_item.get("type") == "reasoning":
                current_item.setdefault("summary", []).append(
                    cast(dict[str, Any], event.get("part") or {})
                )
            continue

        if event_type == "response.reasoning_summary_text.delta":
            if (
                current_item
                and current_item.get("type") == "reasoning"
                and isinstance(current_block, ThinkingContent)
            ):
                summary = cast(list[dict[str, Any]], current_item.setdefault("summary", []))
                if summary:
                    summary[-1]["text"] = cast(str, summary[-1].get("text") or "") + cast(
                        str,
                        event.get("delta") or "",
                    )
                delta = cast(str, event.get("delta") or "")
                current_block.thinking += delta
                stream.push(
                    ThinkingDeltaEvent(
                        content_index=len(output.content) - 1,
                        delta=delta,
                        partial=output,
                    )
                )
            continue

        if event_type == "response.reasoning_summary_part.done":
            if (
                current_item
                and current_item.get("type") == "reasoning"
                and isinstance(current_block, ThinkingContent)
            ):
                summary = cast(list[dict[str, Any]], current_item.setdefault("summary", []))
                if summary:
                    summary[-1]["text"] = cast(str, summary[-1].get("text") or "") + "\n\n"
                    current_block.thinking += "\n\n"
                    stream.push(
                        ThinkingDeltaEvent(
                            content_index=len(output.content) - 1,
                            delta="\n\n",
                            partial=output,
                        )
                    )
            continue

        if event_type == "response.content_part.added":
            if current_item and current_item.get("type") == "message":
                current_item.setdefault("content", [])
                part = cast(dict[str, Any], event.get("part") or {})
                if part.get("type") in {"output_text", "refusal"}:
                    cast(list[dict[str, Any]], current_item["content"]).append(part)
            continue

        if event_type in {"response.output_text.delta", "response.refusal.delta"}:
            if (
                current_item
                and current_item.get("type") == "message"
                and isinstance(current_block, TextContent)
            ):
                content = cast(list[dict[str, Any]], current_item.get("content") or [])
                if not content:
                    continue
                last_part = content[-1]
                expected_type = (
                    "output_text" if event_type == "response.output_text.delta" else "refusal"
                )
                if last_part.get("type") != expected_type:
                    continue
                delta = cast(str, event.get("delta") or "")
                key = "text" if expected_type == "output_text" else "refusal"
                last_part[key] = cast(str, last_part.get(key) or "") + delta
                current_block.text += delta
                stream.push(
                    TextDeltaEvent(
                        content_index=len(output.content) - 1,
                        delta=delta,
                        partial=output,
                    )
                )
            continue

        if event_type == "response.function_call_arguments.delta":
            if (
                current_item
                and current_item.get("type") == "function_call"
                and isinstance(current_block, ToolCall)
            ):
                delta = cast(str, event.get("delta") or "")
                current_tool_partial_json += delta
                current_block.arguments = parse_streaming_json(current_tool_partial_json)
                stream.push(
                    ToolCallDeltaEvent(
                        content_index=len(output.content) - 1,
                        delta=delta,
                        partial=output,
                    )
                )
            continue

        if event_type == "response.function_call_arguments.done":
            if (
                current_item
                and current_item.get("type") == "function_call"
                and isinstance(current_block, ToolCall)
            ):
                previous_partial_json = current_tool_partial_json
                current_tool_partial_json = cast(str, event.get("arguments") or "")
                current_block.arguments = parse_streaming_json(current_tool_partial_json)
                if current_tool_partial_json.startswith(previous_partial_json):
                    delta = current_tool_partial_json[len(previous_partial_json):]
                    if delta:
                        stream.push(
                            ToolCallDeltaEvent(
                                content_index=len(output.content) - 1,
                                delta=delta,
                                partial=output,
                            )
                        )
            continue

        if event_type == "response.output_item.done":
            item = cast(dict[str, Any], event.get("item") or {})
            item_type = item.get("type")
            content_index = len(output.content) - 1
            if item_type == "reasoning" and isinstance(current_block, ThinkingContent):
                summary = cast(list[dict[str, Any]], item.get("summary") or [])
                current_block.thinking = "\n\n".join(
                    cast(str, part.get("text") or "") for part in summary if part.get("text")
                )
                current_block.thinking_signature = json.dumps(item)
                stream.push(
                    ThinkingEndEvent(
                        content_index=content_index,
                        content=current_block.thinking,
                        partial=output,
                    )
                )
                current_block = None
                continue

            if item_type == "message" and isinstance(current_block, TextContent):
                content = cast(list[dict[str, Any]], item.get("content") or [])
                current_block.text = "".join(
                    cast(str, part.get("text") or part.get("refusal") or "") for part in content
                )
                current_block.text_signature = _encode_text_signature_v1(
                    cast(str, item.get("id") or ""),
                    cast(TextPhase | None, item.get("phase")),
                )
                stream.push(
                    TextEndEvent(
                        content_index=content_index,
                        content=current_block.text,
                        partial=output,
                    )
                )
                current_block = None
                continue

            if item_type == "function_call" and isinstance(current_block, ToolCall):
                current_block.arguments = (
                    parse_streaming_json(current_tool_partial_json)
                    if current_tool_partial_json
                    else parse_streaming_json(cast(str, item.get("arguments") or "{}"))
                )
                stream.push(
                    ToolCallEndEvent(
                        content_index=content_index,
                        tool_call=current_block,
                        partial=output,
                    )
                )
                current_block = None
                current_tool_partial_json = ""
            continue

        if event_type == "response.completed":
            response = cast(dict[str, Any], event.get("response") or {})
            if response.get("id"):
                output.response_id = cast(str, response.get("id"))
            usage_data = cast(dict[str, Any], response.get("usage") or {})
            cached_tokens = int(
                cast(dict[str, Any], usage_data.get("input_tokens_details") or {}).get(
                    "cached_tokens"
                )
                or 0
            )
            if usage_data:
                output.usage = Usage(
                    input=max(int(usage_data.get("input_tokens") or 0) - cached_tokens, 0),
                    output=int(usage_data.get("output_tokens") or 0),
                    cache_read=cached_tokens,
                    cache_write=0,
                    total_tokens=int(usage_data.get("total_tokens") or 0),
                )
            calculate_cost(model, output.usage)
            if options and options.apply_service_tier_pricing is not None:
                options.apply_service_tier_pricing(
                    output.usage,
                    cast(str | None, response.get("service_tier")) or options.service_tier,
                )
            output.stop_reason = map_openai_responses_status(
                cast(str | None, response.get("status"))
            )
            if (
                any(block.type == "toolCall" for block in output.content)
                and output.stop_reason == "stop"
            ):
                output.stop_reason = "toolUse"
            continue

        if event_type == "error":
            code = event.get("code")
            message = event.get("message")
            raise RuntimeError(
                f"Error Code {code}: {message}" if code or message else "Unknown error"
            )

        if event_type == "response.failed":
            response = cast(dict[str, Any], event.get("response") or {})
            error = cast(dict[str, Any], response.get("error") or {})
            details = cast(dict[str, Any], response.get("incomplete_details") or {})
            if error:
                raise RuntimeError(
                    f"{error.get('code', 'unknown')}: {error.get('message', 'no message')}"
                )
            if details.get("reason"):
                raise RuntimeError(f"incomplete: {details['reason']}")
            raise RuntimeError("Unknown error (no error details in response)")


def map_openai_responses_status(status: str | None) -> StopReason:
    if not status or status == "completed":
        return "stop"
    if status == "incomplete":
        return "length"
    if status in {"failed", "cancelled"}:
        return "error"
    if status in {"queued", "in_progress"}:
        return "stop"
    raise ValueError(f"Unhandled OpenAI Responses status: {status}")


def _encode_text_signature_v1(message_id: str, phase: TextPhase | None = None) -> str:
    payload: dict[str, Any] = {"v": 1, "id": message_id}
    if phase is not None:
        payload["phase"] = phase
    return json.dumps(payload)


def _parse_text_signature(signature: str | None) -> tuple[str, TextPhase | None] | None:
    if not signature:
        return None
    if signature.startswith("{"):
        try:
            parsed = cast(dict[str, Any], json.loads(signature))
        except json.JSONDecodeError:
            return (signature, None)
        if parsed.get("v") == 1 and isinstance(parsed.get("id"), str):
            phase = parsed.get("phase")
            if phase in {"commentary", "final_answer"}:
                return cast(str, parsed["id"]), cast(TextPhase, phase)
            return cast(str, parsed["id"]), None
    return signature, None


def _normalize_id_part(part: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in part)
    return sanitized[:64].rstrip("_") or "id"


def _build_foreign_responses_item_id(item_id: str) -> str:
    normalized = f"fc_{short_hash(item_id)}"
    return normalized[:64]
