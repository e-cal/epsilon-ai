"""Tool definitions, tool-call handling, and tool-result follow-up.

epsilon.llm uses plain JSON Schema dicts for tool parameters (the TypeScript
version uses TypeBox; the wire format is the same JSON Schema either way).
"""

from __future__ import annotations

import asyncio
import json

from epsilon.llm import (
    Context,
    TextContent,
    Tool,
    ToolResultMessage,
    UserMessage,
    complete_async,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_text,
    faux_tool_call,
    register_faux_provider,
)


def _now_iso(timezone: str) -> str:
    return f"current time in {timezone} (mocked)"


def _execute(name: str, arguments: dict[str, object]) -> str:
    if name == "get_time":
        timezone = str(arguments.get("timezone") or "UTC")
        return _now_iso(timezone)
    return f"Unknown tool: {name}"


async def main() -> None:
    registration = register_faux_provider()
    try:
        # Script two assistant responses: first a tool call, then the final answer.
        registration.set_responses(
            [
                faux_assistant_message(
                    [faux_tool_call("get_time", {"timezone": "America/New_York"})],
                    stop_reason="toolUse",
                ),
                faux_assistant_message(
                    [faux_text("It is now early evening in New York.")],
                ),
            ]
        )
        model = registration.get_model()

        tools: list[Tool] = [
            Tool(
                name="get_time",
                description="Get the current time",
                parameters={
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "Optional timezone (e.g. America/New_York)",
                        },
                    },
                },
            )
        ]

        context = Context(
            system_prompt="You are a helpful assistant.",
            messages=[UserMessage(content="What time is it in New York?")],
            tools=tools,
        )

        first = await complete_async(model, context)
        context.messages.append(first)

        for block in first.content:
            if block.type == "toolCall":
                result_text = _execute(block.name, dict(block.arguments))
                context.messages.append(
                    ToolResultMessage(
                        tool_call_id=block.id,
                        tool_name=block.name,
                        content=[TextContent(text=json.dumps(result_text))],
                        is_error=False,
                    )
                )

        # Continue the loop until the model stops calling tools.
        second = await complete_async(model, context)
        context.messages.append(second)

        for block in second.content:
            if block.type == "text":
                print(block.text)
    finally:
        registration.unregister()


if __name__ == "__main__":
    asyncio.run(main())
