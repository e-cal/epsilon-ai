"""Reasoning/thinking content blocks.

The faux provider lets you script `ThinkingContent` blocks alongside text so
the event sequence matches Anthropic and OpenAI Responses reasoning streams.
"""

from __future__ import annotations

import asyncio

from epsilon.llm import (
    Context,
    StreamOptions,
    UserMessage,
    stream,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_text,
    faux_thinking,
    register_faux_provider,
)


async def main() -> None:
    registration = register_faux_provider(tokens_per_second=20)
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_thinking("Let me consider the question carefully."),
                        faux_text("The answer is 42."),
                    ]
                )
            ]
        )
        model = registration.get_model()

        context = Context(
            system_prompt="You are a helpful assistant.",
            messages=[UserMessage(content="What is the meaning of life?")],
        )

        # reasoning level is forwarded as a unified `ReasoningLevel` and translated
        # per provider (Anthropic thinking_budget, OpenAI reasoning effort, etc.).
        options = StreamOptions(reasoning="medium")

        s = stream(model, context, options)
        async for event in s:
            match event.type:
                case "thinking_start":
                    print("[thinking...]")
                case "thinking_delta":
                    print(f"  think: {event.delta!r}")
                case "thinking_end":
                    print(f"[/thinking content={event.content!r}]")
                case "text_delta":
                    print(f"  text: {event.delta!r}")
                case "done":
                    print(f"[done reason={event.reason}]")

        final = await s.result()
        for block in final.content:
            if block.type == "thinking":
                print(f"\nfinal thinking: {block.thinking}")
            elif block.type == "text":
                print(f"final text:     {block.text}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
