# Sketch: minimal client usage

Status: **design sketch**. Names below are proposals.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/01-minimal.ts`.

## Proposed surface

```python
import asyncio
import sys

from epsilon.client import Client


async def main() -> None:
    # Standalone mode: spawns an in-process epsilon.server bound to loopback
    # against the current working directory. Defaults discover skills,
    # extensions, tools, context files from cwd and ~/.epsilon/agent.
    async with Client.standalone() as client:
        session = await client.create_session()

        async for event in session.events():
            if event.type == "message_update":
                sub = event.assistant_message_event
                if sub.type == "text_delta":
                    sys.stdout.write(sub.delta)
                    sys.stdout.flush()
            elif event.type == "agent_end":
                break

        await session.prompt("What files are in the current directory?")


if __name__ == "__main__":
    asyncio.run(main())
```

## Comparison to upstream

```typescript
// pi-mono/packages/coding-agent/examples/sdk/01-minimal.ts
const { session } = await createAgentSession();

session.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await session.prompt("What files are in the current directory?");
```

Differences:

- `createAgentSession()` returns an in-process session; epsilon's
  `Client.standalone()` spawns a local server and returns a client that
  wraps it. The server-first principle removes the in-process API path.
- `session.subscribe(callback)` becomes `async for event in session.events()`
  to fit Python's `AsyncIterator` conventions. A callback-style helper
  (`session.on(handler)`) may also exist for parity.
- The session's `events()` stream is the wire-level event stream from
  `epsilon.server`; ordering and field names match `epsilon.harness`.

## Open questions

- `events()` is one async iterator per session; do we allow multiple
  concurrent consumers (fan-out) or require explicit `tee`?
- `session.dispose()` vs context manager (`async with session: ...`); a
  context manager is the simpler default.
