# Sketch: tools — built-in allowlist + custom tools

Status: **design sketch**.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/05-tools.ts` and
`06-extensions.ts`.

## Proposed surface

### Built-in tool allowlist

```python
import asyncio

from epsilon.client import Client


async def main() -> None:
    async with Client.standalone() as client:
        # Read-only mode: no edit, no write, no bash.
        read_only = await client.create_session(
            tools=["read", "grep", "find", "ls"],
        )
        await read_only.prompt("Inventory the test suite.")

        # Custom selection
        narrow = await client.create_session(
            tools=["read", "bash", "grep"],
            cwd="/path/to/project",
        )
        await narrow.prompt("Find every TODO and group them by file.")


if __name__ == "__main__":
    asyncio.run(main())
```

### Custom tools

Custom tools have to execute somewhere. Two proposed paths:

1. **Server-resident custom tools**: register the tool with the server at
   startup (out-of-band, via a plugin). The client only references it by
   name in `tools=[...]`.
2. **Client-resident custom tools**: tool execution happens in the client
   process; the server proxies tool calls back over the wire.

The TUI use case wants (2) (interactive prompts, local-only state). The
hosted use case wants (1) (sandboxing). Both are likely needed.

```python
# Client-resident tool, executed in the client process
from epsilon.client import Client, ClientTool, ClientToolResult
from epsilon.llm import TextContent


async def execute_echo(_call_id, params, _signal, _on_update):
    return ClientToolResult(
        content=[TextContent(text=f"echoed: {params['value']}")],
        details={"value": params["value"]},
    )


echo = ClientTool(
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


async def main() -> None:
    async with Client.standalone() as client:
        session = await client.create_session(
            tools=["read", "bash", "echo"],
            custom_tools=[echo],
        )
        await session.prompt("Echo hello.")
```

When the server hits `echo`, it emits a `tool_proxy_request` over the wire;
the client invokes `execute_echo` and POSTs the `ClientToolResult` back.
Event ordering mirrors `epsilon.harness.types`.

## Open questions

- proxy framing: piggyback on the SSE event stream + a paired POST
  endpoint, or open a WebSocket; the SSE + POST shape keeps the protocol
  uniform but adds correlation overhead.
- timeout handling for client-side tool execution when the client is
  embedded vs hosted.
- whether `tools=[...]` is a strict allowlist or a starting set the agent
  can request to extend via permissions.
