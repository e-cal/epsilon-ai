"""Minimal Agent usage."""

from __future__ import annotations

import asyncio
import sys

from epsilon.harness import Agent, AgentInitialState
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    registration = register_faux_provider(tokens_per_second=30)
    try:
        registration.set_responses(
            [faux_assistant_message("Hello! I am a helpful assistant.")]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            ),
        )

        def on_event(event, _signal):
            if event.type == "message_update":
                sub = event.assistant_message_event
                if sub.type == "text_delta":
                    sys.stdout.write(sub.delta)
                    sys.stdout.flush()

        agent.subscribe(on_event)

        await agent.prompt("Hello!")
        print()  # newline after streamed deltas
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
