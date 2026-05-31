# Sketch: full control — replace everything, no discovery

Status: **design sketch**.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/12-full-control.ts`.

## Proposed surface

```python
import asyncio
import os

from epsilon.client import Client, ClientTool, ClientToolResult
from epsilon.llm import TextContent, get_model


async def execute_my_tool(_call_id, params, _signal, _on_update):
    return ClientToolResult(
        content=[TextContent(text=f"my_tool ran with {params!r}")],
        details=None,
    )


my_tool = ClientTool(
    name="my_tool",
    label="My Tool",
    description="Demo client-resident tool.",
    parameters={"type": "object", "properties": {}},
    execute=execute_my_tool,
)


async def main() -> None:
    async with Client.standalone() as client:
        session = await client.create_session(
            model=get_model("anthropic", "claude-sonnet-4-5"),
            thinking_level="high",

            # Replace the prompt entirely; no discovery from cwd or agent_dir.
            system_prompt_override="You are a focused code assistant.",

            # Strict allowlist; no built-in tools beyond these names.
            tools=["read", "bash", "my_tool"],
            custom_tools=[my_tool],

            # No skill discovery, no context files, no extensions
            resource_discovery="off",

            # Per-call API key (bypasses server-side auth storage entirely)
            api_keys={"anthropic": os.environ["MY_ANTHROPIC_KEY"]},

            # Non-persistent
            persistence="memory",

            # Override compaction / retry / terminal settings
            settings={
                "compaction": {"strategy": "none"},
                "retry": {"max_delay_ms": 5_000},
            },
        )
        await session.prompt("Run a quick health check.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Comparison to upstream

The upstream "full control" example replaces the auth storage, model
registry, resource loader, session manager, and settings manager. In
epsilon those concerns live behind the server, so the client surface is a
flatter dict of overrides:

| Upstream | epsilon |
|----------|---------|
| `AuthStorage.create("/my/auth.json")` + `setRuntimeApiKey(...)` | `api_keys={...}` |
| `ModelRegistry.create(...)` | implicit; `model=` is pre-resolved |
| `DefaultResourceLoader({ systemPromptOverride, extensionFactories, skillsOverride, agentsFilesOverride, promptsOverride })` | `system_prompt_override`, `resource_discovery="off"`, plus future `resource_overrides=` |
| `SessionManager.inMemory()` | `persistence="memory"` |
| `SettingsManager.inMemory()` | `settings={...}` |

## Open questions

- whether `resource_discovery="off"` is a single flag or fine-grained
  (`skills="off"`, `context_files="off"`, `extensions="off"`); upstream is
  fine-grained, so likely the same here
- `resource_overrides=` shape: passing skill / prompt / extension content
  inline at session create vs registering them on the server; inline keeps
  the standalone story self-contained
