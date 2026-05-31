"""Abort mid-stream, then re-prompt to retry.

`abort()` sets the active run's abort signal; the assistant message is
finalized with `stop_reason="aborted"` and recorded in `state.messages`.

The aborted assistant message **is** the tail of the conversation after
abort, so `continue_()` cannot run from there (it requires the tail to be
`user` or `toolResult`). To retry, send a new `prompt()` instead.

`continue_()` is the right call only when the tail is a `user` /
`toolResult` message — for example, recovering from an LLM error before
the assistant message was finalized, or after manually appending a
`toolResult` to state.
"""

from __future__ import annotations

import asyncio
from typing import cast

from epsilon.harness import Agent, AgentInitialState
from epsilon.llm import AssistantMessage
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Condition was not met before timeout")
        await asyncio.sleep(0.001)


async def main() -> None:
    registration = register_faux_provider(
        tokens_per_second=20,
        token_size={"min": 2, "max": 2},
    )
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    "one two three four five six seven eight nine ten "
                    "eleven twelve thirteen fourteen fifteen"
                ),
                faux_assistant_message("retry succeeded"),
            ]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            ),
        )

        prompt_task = asyncio.create_task(agent.prompt("Count slowly from 1 to 20."))
        await _wait_until(lambda: agent.state.streaming_message is not None)
        await asyncio.sleep(0.03)
        agent.abort()
        await prompt_task

        last = cast(AssistantMessage, agent.state.messages[-1])
        print(f"after abort: stop_reason={last.stop_reason} error={last.error_message!r}")

        # Tail is the aborted assistant message — continue_() would refuse.
        # Issue a fresh prompt to retry; the second queued faux response runs.
        await agent.prompt("Please try again.")
        final = agent.state.messages[-1]
        content = getattr(final, "content", [])
        text = "\n".join(
            block.text for block in content if getattr(block, "type", None) == "text"
        )
        print(f"after retry: {text}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
