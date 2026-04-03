# e-ai

Unified LLM API for the Python port with model discovery, provider routing, streaming assistant events, tool calling, token and cost tracking, and transferable conversation context.

This package currently targets parity for a limited provider set:

- OpenAI Responses API
- Azure OpenAI Responses API
- Anthropic Messages API
- Faux test provider

Only tool-capable models are included.

## Supported Providers

- `openai`
- `azure-openai-responses`
- `anthropic`
- `faux` via `register_faux_provider()` for tests

## Installation

This package lives inside the `py-mono` workspace.

From the repo root:

```bash
uv sync --all-packages
```

## Quick Start

```python
import asyncio

from e_ai import (
    Context,
    StreamOptions,
    TextContent,
    Tool,
    ToolResultMessage,
    UserMessage,
    complete,
    get_model,
    stream,
)


async def main() -> None:
    model = get_model("openai", "gpt-4o-mini")

    tools = [
        Tool(
            name="get_time",
            description="Get the current UTC time.",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "Optional IANA timezone."}
                },
            },
        )
    ]

    context = Context(
        system_prompt="You are a helpful assistant.",
        messages=[UserMessage(content="What time is it?", timestamp=1)],
        tools=tools,
    )

    s = stream(model, context, StreamOptions())

    async for event in s:
        match event.type:
            case "start":
                print(f"starting {event.partial.provider}/{event.partial.model}")
            case "text_delta":
                print(event.delta, end="")
            case "thinking_delta":
                print(event.delta, end="")
            case "toolcall_end":
                print(f"\nTool call: {event.tool_call.name} {event.tool_call.arguments}")
            case "done":
                print(f"\nDone: {event.reason}")
            case "error":
                print(f"\nError: {event.error.error_message}")

    final_message = await s.result()
    context.messages.append(final_message)

    tool_calls = [block for block in final_message.content if block.type == "toolCall"]
    for call in tool_calls:
        result = "2026-04-03 12:00:00 UTC"
        context.messages.append(
            ToolResultMessage(
                tool_call_id=call.id,
                tool_name=call.name,
                content=[TextContent(text=result)],
                is_error=False,
                timestamp=2,
            )
        )

    if tool_calls:
        continuation = await complete(model, context)
        context.messages.append(continuation)


asyncio.run(main())
```

## Streaming Events

`stream()` yields normalized assistant events across providers:

- `start`
- `text_start`
- `text_delta`
- `text_end`
- `thinking_start`
- `thinking_delta`
- `thinking_end`
- `toolcall_start`
- `toolcall_delta`
- `toolcall_end`
- `done`
- `error`

During `toolcall_delta`, `event.partial.content[event.content_index]` contains the best-effort parse of the partial JSON arguments seen so far. Treat it as incomplete until `toolcall_end`.

## Complete vs Stream

- `stream(model, context, options)` returns an `AssistantMessageEventStream`
- `complete(model, context, options)` returns the final `AssistantMessage`
- `stream_simple(...)` and `complete_simple(...)` expose the simplified reasoning interface

## Tools

Tools are plain structured definitions:

```python
from e_ai import Tool

tool = Tool(
    name="get_weather",
    description="Get the weather for a city.",
    parameters={
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "units": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["location"],
    },
)
```

Tool results are conversation messages and can contain text and images.

## Images

Models advertise supported input types via `model.input`.

- If `"image" in model.input`, user messages and tool results may include `ImageContent`
- For non-vision models, images are ignored during provider payload conversion

## Thinking / Reasoning

Use the simplified interface for cross-provider reasoning control:

```python
from e_ai import Context, SimpleStreamOptions, complete_simple, get_model

model = get_model("anthropic", "claude-sonnet-4-5")

response = await complete_simple(
    model,
    Context(messages=[]),
    SimpleStreamOptions(reasoning="medium"),
)
```

Provider-specific options are also exposed:

- `OpenAIResponsesOptions`
- `AzureOpenAIResponsesOptions`
- `AnthropicOptions`

Not every provider uses the same native reasoning controls, but the package maps them onto shared event/content semantics.

## Models and Providers

```python
from e_ai import get_model, get_models, get_providers

providers = get_providers()
openai_models = get_models("openai")
model = get_model("openai", "gpt-5-mini")
```

The built-in model catalog currently includes the upstream-relevant selected-provider IDs needed for the current parity scope.

## Environment Variables

### OpenAI

- `OPENAI_API_KEY`

### Anthropic

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_OAUTH_TOKEN`

### Azure OpenAI Responses

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_BASE_URL`
or
- `AZURE_OPENAI_RESOURCE_NAME`

Optional Azure settings:

- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT_NAME_MAP`

`AZURE_OPENAI_DEPLOYMENT_NAME_MAP` uses `model_id=deployment_name` pairs separated by commas.

Example:

```text
gpt-4o-mini=prod-mini,gpt-5-mini=prod-five
```

## Faux Provider

The faux provider is intended for deterministic tests and local harnesses.

```python
from e_ai import faux_assistant_message, register_faux_provider

registration = register_faux_provider()
registration.set_responses([faux_assistant_message("hello")])
model = registration.get_model()
```

It supports:

- queued responses
- async response factories
- chunked streaming deltas
- abort simulation
- per-session prompt cache simulation

## Provider Registration

Built-in provider registration is currently not lazy.

What that means:

- importing `e_ai.stream` registers built-in providers immediately
- the built-in provider modules are imported eagerly during that registration path
- missing or broken imports in those built-in provider modules fail at import time rather than the first call to a specific provider
- startup/import cost is slightly higher than the upstream TS package, which uses lazy registration wrappers

Current tradeoff:

- simpler Python control flow and easier debugging now
- less isolation for optional provider dependencies later

This is a known structural difference from upstream, not a behavioral limitation for the currently selected providers.

## Current Scope Notes

- The package aims at parity with `pi-mono/packages/ai` for the selected providers only
- OpenAI Responses and Azure OpenAI Responses share most response semantics but still differ in auth, base URL, API version, and deployment handling
- The package-local Python package lives at `packages/ai/e_ai/`
