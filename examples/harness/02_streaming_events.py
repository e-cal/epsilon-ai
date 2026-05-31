"""Full subscribe() event walkthrough.

This subscribes to every AgentEvent variant and prints a labeled trace, so
the output doubles as the canonical event-sequence reference for the
runtime.
"""

from __future__ import annotations

import asyncio

from epsilon.harness import Agent, AgentInitialState
from epsilon.llm.providers import faux_assistant_message, register_faux_provider


async def main() -> None:
    registration = register_faux_provider(tokens_per_second=30)
    try:
        registration.set_responses([faux_assistant_message("Two plus two is four.")])

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            ),
        )

        def on_event(event, _signal):
            match event.type:
                case "agent_start":
                    print("[agent_start]")
                case "turn_start":
                    print("  [turn_start]")
                case "message_start":
                    role = getattr(event.message, "role", "?")
                    print(f"    [message_start role={role}]")
                case "message_update":
                    sub = event.assistant_message_event
                    print(f"      [message_update {sub.type}]")
                case "message_end":
                    role = getattr(event.message, "role", "?")
                    print(f"    [message_end role={role}]")
                case "tool_execution_start":
                    print(f"    [tool_start name={event.tool_name}]")
                case "tool_execution_update":
                    print(f"    [tool_update name={event.tool_name}]")
                case "tool_execution_end":
                    print(f"    [tool_end name={event.tool_name} is_error={event.is_error}]")
                case "turn_end":
                    print(f"  [turn_end tool_results={len(event.tool_results)}]")
                case "agent_end":
                    print(f"[agent_end messages={len(event.messages)}]")

        agent.subscribe(on_event)
        await agent.prompt("What is 2 + 2?")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
