from __future__ import annotations

from e_ai import AssistantMessage, Context, TextContent, ThinkingContent, ToolCall, ToolResultMessage, Usage, UserMessage
from e_ai.models import get_model
from e_ai.providers.anthropic import normalize_anthropic_tool_call_id
from e_ai.providers.transform_messages import transform_messages


def test_transform_messages_converts_cross_model_thinking_to_text() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    messages = [
        UserMessage(content="hello", timestamp=1),
        AssistantMessage(
            content=[
                ThinkingContent(thinking="Let me think about this...", thinking_signature="reasoning"),
                TextContent(text="Hi there!"),
            ],
            api="openai-responses",
            provider="openai",
            model="gpt-5-mini",
            usage=Usage(),
            stop_reason="stop",
            timestamp=2,
        ),
    ]

    result = transform_messages(messages, model, normalize_anthropic_tool_call_id)
    assistant = next(message for message in result if message.role == "assistant")

    assert all(block.type != "thinking" for block in assistant.content)
    assert [block.text for block in assistant.content if isinstance(block, TextContent)] == [
        "Let me think about this...",
        "Hi there!",
    ]


def test_transform_messages_strips_thought_signature_when_models_differ() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    assistant = AssistantMessage(
        content=[
            ToolCall(
                id="call_123|fc_123",
                name="bash",
                arguments={"command": "ls"},
                thought_signature='{"id":"rs_1"}',
            )
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-5-mini",
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=2,
    )

    result = transform_messages(
        [UserMessage(content="run a command", timestamp=1), assistant],
        model,
        normalize_anthropic_tool_call_id,
    )
    transformed_assistant = next(message for message in result if message.role == "assistant")
    tool_call = next(block for block in transformed_assistant.content if isinstance(block, ToolCall))

    assert tool_call.thought_signature is None


def test_transform_messages_inserts_missing_tool_result_before_next_user_message() -> None:
    model = get_model("openai", "gpt-5-mini")
    assistant = AssistantMessage(
        content=[ToolCall(id="call_1|fc_1", name="echo", arguments={"message": "hi"})],
        api="openai-responses",
        provider="openai",
        model="gpt-5-mini",
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=2,
    )

    result = transform_messages(
        [
            UserMessage(content="use the tool", timestamp=1),
            assistant,
            UserMessage(content="never mind", timestamp=3),
        ],
        model,
    )

    synthetic_tool_result = next(message for message in result if message.role == "toolResult")
    assert synthetic_tool_result.tool_call_id == "call_1|fc_1"
    assert synthetic_tool_result.is_error is True
    assert synthetic_tool_result.content[0].text == "No result provided"


def test_transform_messages_skips_aborted_and_error_assistant_messages() -> None:
    model = get_model("openai", "gpt-5-mini")

    aborted = AssistantMessage(
        content=[ThinkingContent(thinking="partial", thinking_signature="sig")],
        api="openai-responses",
        provider="openai",
        model="gpt-5-mini",
        usage=Usage(),
        stop_reason="aborted",
        timestamp=2,
    )
    errored = AssistantMessage(
        content=[TextContent(text="broken")],
        api="openai-responses",
        provider="openai",
        model="gpt-5-mini",
        usage=Usage(),
        stop_reason="error",
        timestamp=3,
    )

    result = transform_messages(
        [
            UserMessage(content="hello", timestamp=1),
            aborted,
            errored,
            UserMessage(content="continue", timestamp=4),
        ],
        model,
    )

    assert [message.role for message in result] == ["user", "user"]
