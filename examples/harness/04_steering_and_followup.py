"""Steering and follow-up queues.

While the agent is processing a prompt you cannot call `prompt()` again, but
you can `steer()` (interject) or `follow_up()` (queue a message that will be
delivered on the next turn). Queue modes:

- `"one-at-a-time"` (default): drain one queued message per turn
- `"all"`: drain all queued messages on the next turn

This example queues a follow-up before calling `continue_()` from an
existing conversation state.
"""

from __future__ import annotations

import asyncio

from epsilon.harness import Agent, AgentInitialState
from epsilon.llm import TextContent, UserMessage
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    registration = register_faux_provider()
    try:
        model = registration.get_model()
        registration.set_responses(
            [faux_assistant_message("Processed the queued follow-up.")]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                model=model,
                messages=[
                    UserMessage(content=[TextContent(text="Hello")], timestamp=1),
                    faux_assistant_message(
                        "Hi there!",
                        api=registration.api,
                        provider=registration.provider,
                        model=model.id,
                    ),
                ],
            ),
        )

        # No active run, but we can still seed the follow-up queue.
        agent.follow_up(
            UserMessage(
                content=[TextContent(text="Now answer this follow-up.")],
                timestamp=2,
            )
        )

        # continue_() picks the follow-up off the queue because the tail is assistant.
        await agent.continue_()

        for message in agent.state.messages:
            content = getattr(message, "content", [])
            if isinstance(content, str):
                text = content
            else:
                text = "\n".join(
                    block.text for block in content if getattr(block, "type", None) == "text"
                )
            print(f"{message.role}: {text}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
