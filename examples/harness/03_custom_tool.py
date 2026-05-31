"""Custom AgentTool calling a local Python function.

`AgentTool` packages a name, JSON-schema parameters, and an async `execute`
callable. The runtime emits `tool_execution_start` / `_update` / `_end`
events around the call and feeds the result back as a `ToolResultMessage`.
"""

from __future__ import annotations

import asyncio

from epsilon.harness import (
    Agent,
    AgentInitialState,
    AgentTool,
    AgentToolResult,
)
from epsilon.llm import (
    TextContent,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_text,
    faux_tool_call,
    register_faux_provider,
)


async def execute_echo(_tool_call_id, params, _signal, _on_update):
    assert isinstance(params, dict)
    value = params["value"]
    return AgentToolResult(
        content=[TextContent(text=f"echoed: {value}")],
        details={"value": value},
    )


async def main() -> None:
    registration = register_faux_provider()
    try:
        # First response calls the tool; second response wraps up.
        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_text("Using the echo tool."),
                        faux_tool_call("echo", {"value": "hello"}, tool_call_id="t1"),
                    ],
                    stop_reason="toolUse",
                ),
                faux_assistant_message("done"),
            ]
        )

        echo_tool = AgentTool(
            name="echo",
            label="Echo",
            description="Echo a string.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            execute=execute_echo,
        )

        agent = Agent(
            initial_state=AgentInitialState(
                model=registration.get_model(),
                tools=[echo_tool],
            ),
        )

        def on_event(event, _signal):
            match event.type:
                case "tool_execution_start":
                    print(f"[tool start] {event.tool_name}({event.args!r})")
                case "tool_execution_end":
                    text = "".join(
                        block.text for block in event.result.content if block.type == "text"
                    )
                    print(f"[tool end]   {event.tool_name} -> {text}")

        agent.subscribe(on_event)
        await agent.prompt("Echo hello")

        final = agent.state.messages[-1]
        text = "\n".join(
            block.text for block in getattr(final, "content", []) if block.type == "text"
        )
        print(f"\nfinal: {text}")
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
