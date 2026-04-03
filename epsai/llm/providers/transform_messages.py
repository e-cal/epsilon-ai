from __future__ import annotations

import time
from collections.abc import Callable

from ..types import AssistantMessage, Message, Model, TextContent, ToolCall, ToolResultMessage

NormalizeToolCallId = Callable[[str, Model, AssistantMessage], str]


def transform_messages(
    messages: list[Message],
    model: Model,
    normalize_tool_call_id: NormalizeToolCallId | None = None,
) -> list[Message]:
    tool_call_id_map: dict[str, str] = {}
    transformed: list[Message] = []

    for message in messages:
        if message.role == "user":
            transformed.append(message)
            continue

        if message.role == "toolResult":
            normalized_id = tool_call_id_map.get(message.tool_call_id)
            if normalized_id and normalized_id != message.tool_call_id:
                transformed.append(
                    ToolResultMessage(
                        tool_call_id=normalized_id,
                        tool_name=message.tool_name,
                        content=list(message.content),
                        details=message.details,
                        is_error=message.is_error,
                        timestamp=message.timestamp,
                    )
                )
            else:
                transformed.append(message)
            continue

        is_same_model = (
            message.provider == model.provider
            and message.api == model.api
            and message.model == model.id
        )
        content = []
        for block in message.content:
            if block.type == "thinking":
                if block.redacted:
                    if is_same_model:
                        content.append(block)
                    continue
                if is_same_model and block.thinking_signature:
                    content.append(block)
                    continue
                if not block.thinking.strip():
                    continue
                if is_same_model:
                    content.append(block)
                else:
                    content.append(TextContent(text=block.thinking))
                continue

            if block.type == "text":
                content.append(block if is_same_model else TextContent(text=block.text))
                continue

            normalized_tool_call = block
            if not is_same_model and block.thought_signature:
                normalized_tool_call = ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.arguments,
                )
            if not is_same_model and normalize_tool_call_id is not None:
                normalized_id = normalize_tool_call_id(block.id, model, message)
                if normalized_id != block.id:
                    tool_call_id_map[block.id] = normalized_id
                    normalized_tool_call = ToolCall(
                        id=normalized_id,
                        name=normalized_tool_call.name,
                        arguments=normalized_tool_call.arguments,
                    )
            content.append(normalized_tool_call)

        transformed.append(
            AssistantMessage(
                content=content,
                api=message.api,
                provider=message.provider,
                model=message.model,
                response_id=message.response_id,
                usage=message.usage,
                stop_reason=message.stop_reason,
                error_message=message.error_message,
                timestamp=message.timestamp,
            )
        )

    result: list[Message] = []
    pending_tool_calls: list[ToolCall] = []
    existing_tool_result_ids: set[str] = set()

    for message in transformed:
        if message.role == "assistant":
            if pending_tool_calls:
                _append_missing_tool_results(result, pending_tool_calls, existing_tool_result_ids)
                pending_tool_calls = []
                existing_tool_result_ids = set()

            if message.stop_reason in {"error", "aborted"}:
                continue

            pending_tool_calls = [block for block in message.content if block.type == "toolCall"]
            existing_tool_result_ids = set()
            result.append(message)
            continue

        if message.role == "toolResult":
            existing_tool_result_ids.add(message.tool_call_id)
            result.append(message)
            continue

        if pending_tool_calls:
            _append_missing_tool_results(result, pending_tool_calls, existing_tool_result_ids)
            pending_tool_calls = []
            existing_tool_result_ids = set()
        result.append(message)

    return result


def _append_missing_tool_results(
    result: list[Message],
    pending_tool_calls: list[ToolCall],
    existing_tool_result_ids: set[str],
) -> None:
    timestamp = int(time.time() * 1000)
    for tool_call in pending_tool_calls:
        if tool_call.id in existing_tool_result_ids:
            continue
        result.append(
            ToolResultMessage(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=[TextContent(text="No result provided")],
                is_error=True,
                timestamp=timestamp,
            )
        )
