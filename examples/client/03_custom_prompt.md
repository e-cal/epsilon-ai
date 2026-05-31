# Sketch: custom system prompt

Status: **design sketch**.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/03-custom-prompt.ts`.

## Proposed surface

```python
import asyncio

from epsilon.client import Client


async def main() -> None:
    async with Client.standalone() as client:
        # Append to the default system prompt
        session = await client.create_session(
            system_prompt_suffix="Be concise. Avoid bullet lists.",
        )
        await session.prompt("Summarize the agent loop.")

        # Replace the default system prompt entirely
        replaced = await client.create_session(
            system_prompt_override="You are a terse code reviewer.",
        )
        await replaced.prompt("Review the latest diff.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Comparison to upstream

```typescript
const loader = new DefaultResourceLoader({
  systemPromptOverride: (base) => `${base}\n\nBe concise.`,
});
await loader.reload();
const { session } = await createAgentSession({ resourceLoader: loader, ... });
```

Differences:

- The `DefaultResourceLoader` mechanism is server-side in epsilon. The
  client exposes a small surface (`system_prompt_suffix`,
  `system_prompt_override`) instead of a callable. A callable hook would
  require crossing the wire on every reload, which we want to avoid.
- For richer overrides (per-skill, per-extension), the client will accept
  a `resource_overrides=` payload that the server applies once at session
  create. That surface is still TBD.

## Open questions

- whether `system_prompt_suffix` is appended to the assembled default (the
  upstream `(base) => base + extra` shape) or to the literal base prompt
  before context files are layered in. Leaning toward the former for parity.
