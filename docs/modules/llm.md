# `epsilon.llm`

Unified LLM API for the Python port with model discovery, provider routing, streaming assistant events, tool calling, token and cost tracking, and transferable conversation context.

This package currently targets parity for a limited provider set:

- OpenAI Responses API
- OpenAI Codex Responses API (with OAuth)
- Foundry
- Anthropic Messages API
- Faux test provider

Only tool-capable models are included.

## Intended Deviations

This module intentionally deviates from `pi-mono/packages/ai` in its public API shape.

- Upstream exposes separate simplified and provider-native entrypoints (`streamSimple` / `completeSimple` alongside `stream` / `complete`)
- `epsilon.llm` exposes a single streaming entrypoint `stream()`, plus `complete()` for synchronous completion and `complete_async()` for async completion
- `StreamOptions(...)` is the normalized portable options type, including cross-provider reasoning controls like `reasoning` and `thinking_budgets`
- `epsilon.llm` exposes a Python-specific public reasoning enum surface: `ReasoningLevel = Literal["none", "minimal", "low", "medium", "high", "max", "xhigh"]`
- `epsilon.llm` also exports `REASONING_LEVELS` as the canonical runtime list of valid public reasoning values so callers do not need to introspect the `Literal` alias
- This reasoning API intentionally differs from upstream naming: public `"none"` behaves like omitting reasoning entirely, and public `"max"` or `"xhigh"` both map to the same top-end provider level where applicable
- Provider-native option subclasses such as `OpenAIResponsesOptions` and `AnthropicOptions` are still available when you need direct control of provider-specific fields

Operational rule:

- Pass plain `StreamOptions(...)` when you want the library to normalize reasoning/thinking controls across providers
- Pass a provider-specific subclass when you want native provider semantics

This is an intended design choice, not an incomplete port. The internal provider layer is responsible for handling both cases through the normal `stream()` / completion path.

## Supported Providers

- `openai`
- `openai-codex`
- `foundry`
- `anthropic`
- `faux` via `register_faux_provider()` for tests

## Installation

This module ships inside the `epsilon-ai` distribution.

From the repo root:

```bash
uv sync
```

## Quick Start

```python
import asyncio

from epsilon.llm import (
    Context,
    StreamOptions,
    TextContent,
    Tool,
    ToolResultMessage,
    UserMessage,
    complete_async,
    get_model,
    stream,
)


async def main() -> None:
    model = get_model("openai", "gpt-5.3-codex")

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
        continuation = await complete_async(model, context)
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
- `complete(model, context, options)` runs synchronously and returns the final `AssistantMessage`
- `complete_async(model, context, options)` returns the final `AssistantMessage` for async callers
- Pass `StreamOptions(reasoning=...)` for provider-agnostic reasoning control
- Pass a provider-specific `StreamOptions` subclass when you need native provider fields

Use `complete_async()` inside existing asyncio code. `complete()` is the synchronous wrapper.

This differs intentionally from upstream, which keeps a separate simplified API surface.

## Tools

Tools are plain structured definitions:

```python
from epsilon.llm import Tool

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

Use `StreamOptions` for cross-provider reasoning control:

```python
from epsilon.llm import Context, StreamOptions, complete, get_model


model = get_model("anthropic", "claude-sonnet-4-5")

response = complete(
    model,
    Context(messages=[]),
    StreamOptions(reasoning="medium"),
)
```

Provider-specific options are also exposed:

- `OpenAIResponsesOptions`
- `OpenAICodexResponsesOptions`
- `FoundryOptions`
- `AnthropicOptions` (with `AnthropicEffort` and `AnthropicThinkingDisplay`)

Not every provider uses the same native reasoning controls, but the package maps them onto shared event/content semantics.

Intentional deviation from upstream:

- Import `ReasoningLevel` for the public type alias
- Import `REASONING_LEVELS` when you need the runtime list of valid values
- Both `"max"` and `"xhigh"` are accepted on the user-facing API and normalize to the same behavior
- Prefer `"max"` in docs and examples; `"xhigh"` is accepted as an alias for intuition/backwards-familiarity

### Anthropic thinking display

`AnthropicOptions.thinking_display` controls how thinking content is returned:

- `"summarized"` (default here): thinking blocks contain summarized thinking text
- `"omitted"`: thinking blocks return an empty thinking field; the encrypted signature still travels back for multi-turn continuity

Anthropic's native default for Opus 4.7 is `"omitted"`; the port overrides the default to `"summarized"` to match older Claude 4 behavior, mirroring upstream.

## Models and Providers

```python
from epsilon.llm import get_model, get_models, get_providers

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

### Foundry

- `FOUNDRY_API_KEY`
- `FOUNDRY_OPENAI_BASE_URL`
- `FOUNDRY_ANTHROPIC_BASE_URL`
or
- `FOUNDRY_PROJECT`

Optional Foundry settings:

- `FOUNDRY_API_VERSION`
- `FOUNDRY_DEPLOYMENT_NAME_MAP`

`FOUNDRY_DEPLOYMENT_NAME_MAP` uses `model_id=deployment_name` pairs separated by commas.

Example:

```text
gpt-4o-mini=prod-mini,gpt-5-mini=prod-five
```

Foundry endpoint selection:

- Claude models default to the Foundry Anthropic endpoint
- Other models default to the OpenAI-compatible Foundry endpoint
- Use `FoundryOptions(foundry_endpoint="anthropic")` or `FoundryOptions(foundry_endpoint="openai")` when a custom deployment name needs an explicit route

## Faux Provider

The faux provider is intended for deterministic tests and local harnesses.

```python
from epsilon.llm import faux_assistant_message, register_faux_provider

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

- importing `epsilon.llm.stream` registers built-in providers immediately
- the built-in provider modules are imported eagerly during that registration path
- missing or broken imports in those built-in provider modules fail at import time rather than the first call to a specific provider
- startup/import cost is slightly higher than the upstream TS package, which uses lazy registration wrappers

Current tradeoff:

- simpler Python control flow and easier debugging now
- less isolation for optional provider dependencies later

This is a known structural difference from upstream, not a behavioral limitation for the currently selected providers.

## Current Scope Notes

- The module aims at parity with `pi-mono/packages/ai` for the selected providers only
- Foundry reuses the OpenAI-compatible Responses transport for GPT-style and other OpenAI-compatible deployments, and the Anthropic Messages transport for Claude deployments
- OpenAI Codex Responses is available for ChatGPT-account-backed OAuth usage and is kept in lockstep with upstream service-tier handling
- The Python source lives at `epsilon/llm/`

## Recent upstream parity sync

- Anthropic: Opus 4.7 added to `supports_xhigh` and adaptive thinking; `AnthropicEffort` now includes `"xhigh"`; thinking config carries a `display` field (`"summarized"` / `"omitted"`); tool cache control is attached to the last tool definition separately from the transcript cache control (pi-mono d1c6cb1e, acbf8eca, 1c016cb0)
- OpenAI Responses / Codex: `session_id` and `x-client-request-id` headers are now set on every openai-responses call whenever a `session_id` is supplied and cache retention is not `"none"` (pi-mono 45f1a2cd, 018b40c3)
- OpenAI Codex: `service_tier` is accepted in `OpenAICodexResponsesOptions` and propagated to the payload and pricing path, including the "trust requested tier" resolver (pi-mono f829f808, 2cdac738)
- `OPENAI_TOOL_CALL_PROVIDERS` and the Foundry OpenAI-compatible transport now accept the upstream allowed-provider sets for tool-call id normalization
- OpenAI-compatible reasoning normalization still gates xhigh via `supports_xhigh(model)` instead of a hard-coded model id prefix
