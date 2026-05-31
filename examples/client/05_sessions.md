# Sketch: sessions — in-memory, persistent, resume, list

Status: **design sketch**.

Mirrors `pi-mono/packages/coding-agent/examples/sdk/11-sessions.ts`.

## Proposed surface

```python
import asyncio

from epsilon.client import Client


async def main() -> None:
    async with Client.standalone() as client:
        # In-memory: no persistence
        ephemeral = await client.create_session(persistence="memory")
        await ephemeral.prompt("Quick question that no one will read again.")

        # Persistent (default): server stores the session under
        # ~/.epsilon/agent/sessions/<cwd-hash>/<session-id>.jsonl
        s1 = await client.create_session(persistence="disk")
        await s1.prompt("Start a project plan.")
        s1_id = s1.id
        await s1.dispose()

        # Resume by id
        s2 = await client.resume_session(s1_id)
        await s2.prompt("Now add a milestone for next week.")

        # List sessions in this cwd
        for record in await client.list_sessions(cwd="."):
            print(record.id, record.last_message_at, record.title)


if __name__ == "__main__":
    asyncio.run(main())
```

## Comparison to upstream

```typescript
// pi-mono
const { session } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
});

const persistent = await createAgentSession({
  sessionManager: SessionManager.create(cwd),
});

await SessionManager.create(cwd).list();
```

Differences:

- `SessionManager.inMemory()` becomes `persistence="memory"`, a flag on
  the session-create request. The server owns the persistence
  implementation; the client does not see the storage layer.
- `SessionManager.list()` becomes `client.list_sessions(cwd=...)`, an RPC
  to the server.

## Open questions

- forking: `client.fork_session(s1_id)` returns a copy at the current state;
  needs design for whether the fork shares the event log or starts a new
  one
- branching points: upstream supports branching from an arbitrary message;
  the client surface for that is TBD
- multi-process safety: two clients connected to the same server
  resuming the same session — last-write-wins, lock, or session-locked
  per-client; leaning lock with explicit takeover
