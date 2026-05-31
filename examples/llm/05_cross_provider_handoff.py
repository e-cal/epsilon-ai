"""Cross-provider context handoff.

The same `Context` can be passed to a different model; epsilon.llm normalizes
provider-specific fields (signatures, response ids, cache markers) so the
conversation is portable.

Here both models are faux providers registered under distinct names; in real
usage the second call could be `get_model("anthropic", "claude-sonnet-4-...")`
after `get_model("openai", "gpt-5-...")`.
"""

from __future__ import annotations

import asyncio

from epsilon.llm import (
    Context,
    UserMessage,
    complete_async,
)
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    provider_a = register_faux_provider(api="faux-a", provider="faux-a")
    provider_b = register_faux_provider(api="faux-b", provider="faux-b")
    try:
        provider_a.set_responses([faux_assistant_message("First, the planets are eight.")])
        provider_b.set_responses(
            [
                faux_assistant_message(
                    "Picking up where the first model left off: Mercury, Venus, ..."
                )
            ]
        )

        context = Context(
            system_prompt="You are an astronomer.",
            messages=[UserMessage(content="How many planets are there?")],
        )

        first = await complete_async(provider_a.get_model(), context)
        context.messages.append(first)
        print("model A:")
        for block in first.content:
            if block.type == "text":
                print(f"  {block.text}")

        # Append a follow-up user message and hand off the same Context to model B.
        context.messages.append(UserMessage(content="Name them in order."))
        second = await complete_async(provider_b.get_model(), context)
        context.messages.append(second)
        print("\nmodel B:")
        for block in second.content:
            if block.type == "text":
                print(f"  {block.text}")
    finally:
        provider_a.unregister()
        provider_b.unregister()


if __name__ == "__main__":
    asyncio.run(main())
