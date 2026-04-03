from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from e_ai import AssistantMessage, Context, ImageContent, TextContent, ToolCall, ToolResultMessage, Usage, UserMessage
from e_ai.hash_utils import short_hash
from e_ai.models import get_model
from e_ai.providers.openai_responses_shared import (
    convert_responses_messages,
    process_openai_responses_event_stream,
)
from e_ai.providers.shared import create_empty_assistant_message
from e_ai.event_stream import AssistantMessageEventStream

COPILOT_RAW_TOOL_CALL_ID = (
    "call_4VnzVawQXPB9MgYib7CiQFEY|"
    "I9b95oN1wD/cHXKTw3PpRkL6KkCtzTJhUxMouMWYwHeTo2j3htzfSk7YPx2vifiIM4g3A8XXyOj8q4Bt"
    "6SLUG7gqY1E3ELkrkVQNHglRfUmWj84lqxJY+Puieb3VKyX0FB+83TUzn91cDMF/4gzt990IzqVrc+nIb9"
    "RRscRD070Du16q1glydVjWR0SBJsE6TbY/esOjFpqplogQqrajm1eI++f3eLi73R6q7hVusY0QbeFySVxA"
    "BCjhN0lXB04caBe1rzHjYzul6MAXj7uq+0r17VLq+yrtyYhN12wkmFqHeqTyEei6EFPbMy24Nc+IbJlkP0"
    "OCg02W+gOnyBFcbi2ctvJFSOhSjt1CqBdqCnnhwUqXjbWiT0wh3DmLScRgTHmGkaI+oAcQQjfic65nxj+T"
    "nEkReA=="
)


def _capture_stream_events(stream: AssistantMessageEventStream) -> list[object]:
    captured: list[object] = []
    original_push = stream.push

    def push(event: object) -> None:
        captured.append(event)
        original_push(event)

    stream.push = push  # type: ignore[method-assign]
    return captured


async def _aiter(events: list[dict[str, object]]) -> AsyncIterator[dict[str, object]]:
    for event in events:
        yield event


def test_convert_responses_messages_hashes_foreign_tool_call_item_ids() -> None:
    model = get_model("openai", "gpt-5.2-codex")
    assistant = AssistantMessage(
        content=[
            ToolCall(
                id=COPILOT_RAW_TOOL_CALL_ID,
                name="edit",
                arguments={"path": "src/styles/app.css"},
            )
        ],
        api="openai-responses",
        provider="github-copilot",
        model="gpt-5.2-codex",
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=2,
    )
    tool_result = ToolResultMessage(
        tool_call_id=COPILOT_RAW_TOOL_CALL_ID,
        tool_name="edit",
        content=[TextContent(text="ok")],
        is_error=False,
        timestamp=3,
    )
    context = Context(
        system_prompt="You are concise.",
        messages=[UserMessage(content="Use the tool.", timestamp=1), assistant, tool_result],
    )

    payload = convert_responses_messages(model, context, {"openai"})
    function_call = next(item for item in payload if item.get("type") == "function_call")
    expected_item_id = f"fc_{short_hash(COPILOT_RAW_TOOL_CALL_ID.split('|')[1])}"

    assert function_call["id"] == expected_item_id
    assert len(expected_item_id) <= 64


def test_convert_responses_messages_keeps_tool_result_images_in_function_call_output() -> None:
    model = get_model("openai", "gpt-5-mini")
    context = Context(
        messages=[
            UserMessage(content="Call the tool.", timestamp=1),
            AssistantMessage(
                content=[ToolCall(id="call_1|fc_1", name="get_circle", arguments={})],
                api="openai-responses",
                provider="openai",
                model="gpt-5-mini",
                usage=Usage(),
                stop_reason="toolUse",
                timestamp=2,
            ),
            ToolResultMessage(
                tool_call_id="call_1|fc_1",
                tool_name="get_circle",
                content=[
                    TextContent(text="A red circle with a diameter of 100 pixels."),
                    ImageContent(data="Zm9v", mime_type="image/png"),
                ],
                is_error=False,
                timestamp=3,
            ),
        ]
    )

    payload = convert_responses_messages(model, context, {"openai"})
    function_call_output = next(item for item in payload if item.get("type") == "function_call_output")
    output = function_call_output["output"]

    assert isinstance(output, list)
    assert output[0]["type"] == "input_text"
    assert output[1]["type"] == "input_image"


@pytest.mark.asyncio
async def test_process_openai_responses_event_stream_emits_incremental_events() -> None:
    model = get_model("openai", "gpt-5-mini")
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    stream = AssistantMessageEventStream()
    captured = _capture_stream_events(stream)

    events = [
        {"type": "response.created", "response": {"id": "resp_1"}},
        {"type": "response.output_item.added", "item": {"type": "reasoning"}},
        {"type": "response.reasoning_summary_part.added", "part": {"text": ""}},
        {"type": "response.reasoning_summary_text.delta", "delta": "plan"},
        {
            "type": "response.output_item.done",
            "item": {"type": "reasoning", "summary": [{"text": "plan"}]},
        },
        {"type": "response.output_item.added", "item": {"type": "message"}},
        {"type": "response.content_part.added", "part": {"type": "output_text", "text": ""}},
        {"type": "response.output_text.delta", "delta": "hello"},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "id": "msg_1",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "hello"}],
            },
        },
        {
            "type": "response.output_item.added",
            "item": {"type": "function_call", "call_id": "call_1", "id": "fc_1", "name": "echo"},
        },
        {"type": "response.function_call_arguments.delta", "delta": '{"value":2'},
        {"type": "response.function_call_arguments.done", "arguments": '{"value":21}'},
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_1",
                "id": "fc_1",
                "name": "echo",
                "arguments": '{"value":21}',
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "resp_1",
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "total_tokens": 13,
                    "input_tokens_details": {"cached_tokens": 2},
                },
            },
        },
    ]

    await process_openai_responses_event_stream(_aiter(events), output, stream, model)

    event_types = [event.type for event in captured]
    assert event_types == [
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "text_start",
        "text_delta",
        "text_end",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
    ]
    toolcall_delta = captured[7]
    assert toolcall_delta.partial.content[2].arguments == {"value": 2}
    assert output.response_id == "resp_1"
    assert output.stop_reason == "toolUse"
    assert output.usage.input == 8
    assert output.usage.cache_read == 2
    assert output.usage.total_tokens == 13
