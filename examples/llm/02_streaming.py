"""Streaming with full event coverage.

The faux provider emits the same event sequence as real providers, so this
example doubles as the canonical event reference.
"""

from __future__ import annotations

import asyncio

from epsilon.llm import (
    Context,
    UserMessage,
    stream,
)
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    # tokens_per_second slows the faux provider so the delta events are visible.
    registration = register_faux_provider(tokens_per_second=20, token_size={"min": 1, "max": 2})
    try:
        registration.set_responses(
            [faux_assistant_message("Streaming works one token at a time.")]
        )
        model = registration.get_model()

        context = Context(
            system_prompt="You are a helpful assistant.",
            messages=[UserMessage(content="Explain streaming.")],
        )

        s = stream(model, context)

        async for event in s:
            match event.type:
                case "start":
                    print(f"[start model={event.partial.model}]")
                case "text_start":
                    print("[text_start]")
                case "text_delta":
                    print(f"  delta: {event.delta!r}")
                case "text_end":
                    print(f"[text_end content={event.content!r}]")
                case "thinking_start" | "thinking_delta" | "thinking_end":
                    # See 04_thinking.py for a reasoning-focused example.
                    pass
                case "toolcall_start" | "toolcall_delta" | "toolcall_end":
                    # See 03_tools.py for tool-call streaming.
                    pass
                case "done":
                    print(f"[done reason={event.reason}]")
                case "error":
                    print(f"[error reason={event.reason}]")

        final = await s.result()
        print(
            f"\nfinal stop_reason={final.stop_reason} "
            f"tokens in={final.usage.input} out={final.usage.output}"
        )
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
