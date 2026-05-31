# Sketch: custom model and thinking level

Status: **design sketch**.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/02-custom-model.ts`.

## Proposed surface

```python
import asyncio

from epsilon.client import Client
from epsilon.llm import get_model


async def main() -> None:
    async with Client.standalone() as client:
        session = await client.create_session(
            model=get_model("anthropic", "claude-sonnet-4-5"),
            thinking_level="medium",   # "none" | "low" | "medium" | "high" | "xhigh"
        )
        await session.prompt("Explain how the agent loop works.")


if __name__ == "__main__":
    asyncio.run(main())
```

## Comparison to upstream

```typescript
const model = getModel("anthropic", "claude-opus-4-5");
const { session } = await createAgentSession({
  model,
  thinkingLevel: "high",
  authStorage,
  modelRegistry,
});
```

Differences:

- `authStorage` / `modelRegistry` are server-managed. The client trusts the
  server to resolve API keys and known models. A future
  `Client.with_auth(...)` constructor will accept explicit credentials for
  hosted (non-loopback) use.
- `thinking_level` follows Python naming. Values match the unified
  `ReasoningLevel` enum from `epsilon.llm`.

## Open questions

- whether the client takes a raw model dict / id-string and the server
  resolves it, or the client must pre-resolve via `epsilon.llm.get_model()`
  before calling. Pre-resolving keeps the wire payload self-describing and
  matches `pi-mono`; current preference.
