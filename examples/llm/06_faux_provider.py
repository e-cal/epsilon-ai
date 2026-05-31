"""Faux provider as a testing tool.

The faux provider is registered the same way as any real provider, so the
streaming, tool calling, and event semantics it produces match the real
providers. Use this in unit tests for the agent runtime and for harness
integration tests where you do not want to spend tokens.
"""

from __future__ import annotations

import asyncio

from epsilon.llm import (
    Context,
    UserMessage,
    complete_async,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_text,
    faux_tool_call,
    register_faux_provider,
)


async def main() -> None:
    registration = register_faux_provider(
        # control token timing so streaming tests can assert deltas
        tokens_per_second=50,
        token_size={"min": 3, "max": 6},
        # a single registration can host multiple model entries
        models=[
            {
                "id": "faux-fast",
                "name": "Faux Fast",
                "reasoning": False,
                "input": ["text"],
                "context_window": 32_000,
                "max_tokens": 4_096,
            },
            {
                "id": "faux-with-vision",
                "name": "Faux Vision",
                "reasoning": False,
                "input": ["text", "image"],
                "context_window": 128_000,
                "max_tokens": 16_384,
            },
        ],
    )
    try:
        # Script a multi-step run: tool call, then final answer.
        registration.set_responses(
            [
                faux_assistant_message(
                    [faux_tool_call("ping", {"host": "localhost"})],
                    stop_reason="toolUse",
                ),
                faux_assistant_message([faux_text("done.")]),
            ]
        )

        model = registration.get_model("faux-fast")
        context = Context(messages=[UserMessage(content="ping localhost")])

        first = await complete_async(model, context)
        assert first.stop_reason == "toolUse"
        print(f"first response stop_reason: {first.stop_reason}")
        print(f"pending scripted responses: {registration.get_pending_response_count()}")

        # ... the caller would execute the tool, append a ToolResultMessage,
        # then call complete_async() again; here we just consume the next response.
        second = await complete_async(model, context)
        print(f"second response stop_reason: {second.stop_reason}")
        print(f"pending scripted responses: {registration.get_pending_response_count()}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
