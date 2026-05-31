"""Minimal non-streaming completion against the faux provider."""

from __future__ import annotations

import asyncio

from epsilon.llm import (
    Context,
    UserMessage,
    complete_async,
)
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("4")])
        model = registration.get_model()

        context = Context(
            system_prompt="You are a helpful assistant.",
            messages=[UserMessage(content="What is 2 + 2?")],
        )
        print(context)

        response = await complete_async(model, context)

        for block in response.content:
            if block.type == "text":
                print(block.text)

        print(
            f"\nusage: input={response.usage.input} "
            f"output={response.usage.output} "
            f"cost=${response.usage.cost.total:.6f}"
        )

        print(f"\n---\n\nFull response object:\n\n{response}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
