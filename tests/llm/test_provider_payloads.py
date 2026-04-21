from __future__ import annotations

from typing import cast

from epsilon.llm import Context, ImageContent, TextContent, Tool, ToolResultMessage, UserMessage
from epsilon.llm.models import get_model
from epsilon.llm.providers.anthropic import AnthropicOptions, build_anthropic_payload
from epsilon.llm.providers.azure_openai_responses import (
    AzureOpenAIResponsesOptions,
    parse_deployment_name_map,
    resolve_deployment_name,
)
from epsilon.llm.providers.openai_responses import (
    OpenAIResponsesOptions,
    build_openai_responses_payload,
)
from epsilon.llm.types import Message


def test_openai_responses_payload_includes_reasoning_and_tools() -> None:
    model = get_model("openai", "gpt-5-mini")
    context = Context(
        system_prompt="You are helpful.",
        messages=[UserMessage(content="hello", timestamp=1)],
        tools=[
            Tool(
                name="echo",
                description="Echo",
                parameters={"type": "object", "properties": {}},
            )
        ],
    )

    payload = build_openai_responses_payload(
        model,
        context,
        OpenAIResponsesOptions(reasoning_effort="medium", session_id="session-1"),
    )

    assert payload["model"] == "gpt-5-mini"
    assert payload["reasoning"] == {"effort": "medium", "summary": "auto"}
    tools = payload["tools"]
    assert isinstance(tools, list)
    assert tools[0]["name"] == "echo"
    input_items = payload["input"]
    assert isinstance(input_items, list)
    assert input_items[0]["role"] == "developer"


def test_openai_responses_payload_keeps_tool_result_images_in_function_call_output() -> None:
    model = get_model("openai", "gpt-5-mini")
    context = Context(
        messages=cast(
            list[Message],
            [
                UserMessage(content="use the tool", timestamp=1),
                ToolResultMessage(
                    tool_call_id="call_1|fc_1",
                    tool_name="describe_image",
                    content=[
                        TextContent(text="A red circle with a diameter of 100 pixels."),
                        ImageContent(data="Zm9v", mime_type="image/png"),
                    ],
                    is_error=False,
                    timestamp=2,
                ),
            ],
        ),
    )

    payload = build_openai_responses_payload(model, context)
    input_items = payload["input"]
    assert isinstance(input_items, list)
    function_call_output = input_items[-1]
    assert function_call_output["type"] == "function_call_output"
    output = function_call_output["output"]
    assert isinstance(output, list)
    assert output[0]["type"] == "input_text"
    assert output[1]["type"] == "input_image"


def test_anthropic_payload_groups_tool_results_and_applies_cache_control() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    context = Context(
        system_prompt="You are helpful.",
        messages=[
            UserMessage(content="run it", timestamp=1),
            ToolResultMessage(
                tool_call_id="tool_1",
                tool_name="echo",
                content=[TextContent(text="done")],
                is_error=False,
                timestamp=2,
            ),
        ],
    )

    payload = build_anthropic_payload(
        model,
        context,
        AnthropicOptions(thinking_enabled=True, thinking_budget_tokens=2048),
    )

    assert payload["thinking"] == {
        "type": "enabled",
        "budget_tokens": 2048,
        "display": "summarized",
    }
    system_blocks = payload["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "tool_result"
    assert content[0]["cache_control"] == {"type": "ephemeral"}


def test_azure_deployment_name_map_prefers_explicit_override() -> None:
    model = get_model("azure-openai-responses", "gpt-4o-mini")

    mapping = parse_deployment_name_map("gpt-4o-mini=prod-mini,gpt-5-mini=prod-five")

    assert mapping["gpt-4o-mini"] == "prod-mini"
    assert (
        resolve_deployment_name(
            model,
            options=AzureOpenAIResponsesOptions(azure_deployment_name="custom-deploy"),
        )
        == "custom-deploy"
    )


def test_anthropic_build_payload_disables_thinking_for_reasoning_models() -> None:
    model = get_model("anthropic", "claude-opus-4-6")

    payload = build_anthropic_payload(
        model,
        Context(messages=[UserMessage(content="hello", timestamp=1)]),
        AnthropicOptions(thinking_enabled=False),
    )

    assert payload["thinking"] == {"type": "disabled"}
