# Sketch: standalone coding agent — embedded server + client

Status: **design sketch**. Names below are proposals.

## Goal

Run the full coding agent end-to-end in a single Python process:

- start an `epsilon.server` instance bound to loopback on an ephemeral port
- connect an `epsilon.client.Client` to it
- create a session against the current working directory
- send a prompt and stream events to stdout
- tear everything down cleanly on exit

No external server, no daemon, no CLI flags required. This is the shape the
`epsilon` CLI entrypoint and the TUI will both build on.

## Proposed surface — high-level

```python
import asyncio
import sys

from epsilon.client import Client


async def main() -> None:
    # Client.standalone() owns an embedded epsilon.server on loopback.
    # On context exit the server is shut down and all sessions disposed.
    async with Client.standalone() as client:
        session = await client.create_session()

        async def pump() -> None:
            async for event in session.events():
                if event.type == "message_update":
                    sub = event.assistant_message_event
                    if sub.type == "text_delta":
                        sys.stdout.write(sub.delta)
                        sys.stdout.flush()
                elif event.type == "agent_end":
                    return

        pumper = asyncio.create_task(pump())
        await session.prompt("Summarize this repository in one paragraph.")
        await session.wait_for_idle()
        pumper.cancel()


if __name__ == "__main__":
    asyncio.run(main())
```

This is the canonical one-call standalone path. The embedded server, the
loopback transport, and the wire framing are all hidden inside
`Client.standalone()`.

## Proposed surface — lower level

For cases where the caller wants the embedded server visible (logging,
inspection, multiple clients in the same process, tests):

```python
import asyncio

from epsilon.client import Client
from epsilon.server import Server, ServerConfig


async def main() -> None:
    config = ServerConfig(host="127.0.0.1", port=0, cwd=".")

    async with Server.serve(config) as server:
        # Address is assigned after bind; port=0 picks an ephemeral port.
        async with Client.connect(server.address) as client:
            session = await client.create_session()
            await session.prompt("List the top-level files in this repo.")
            await session.wait_for_idle()
```

The two shapes converge on the same `Client` API once connected; nothing
downstream of `client.create_session(...)` cares which one was used.

## Lifecycle

```
Client.standalone()
├── construct ServerConfig(host=127.0.0.1, port=0, cwd=os.getcwd())
├── Server.serve(config).__aenter__
│   ├── bind loopback listener on ephemeral port
│   ├── start transport task
│   └── start harness factory
├── Client.connect(server.address).__aenter__
│   └── open transport, handshake, negotiate event stream
└── yield client

# usage: client.create_session(), session.prompt(), session.events(), ...

Client.standalone().__aexit__
├── Client.disconnect
│   └── close transport, drain pending events
└── Server.shutdown
    ├── abort active runs (cooperative)
    ├── await wait_for_idle on each session
    ├── flush session persistence
    └── close listener
```

If the caller hits Ctrl-C, the context manager unwinds the same way; the
embedded server is responsible for cooperatively aborting in-flight tool
calls and LLM streams.

## Configuration

All the standalone shape adds on top of `examples/client/` is server
lifecycle. Configuration knobs live on the client / session, not on
`Client.standalone()`:

```python
async with Client.standalone() as client:
    session = await client.create_session(
        model=...,
        thinking_level="high",
        tools=["read", "bash"],
        custom_tools=[...],
        system_prompt_override=...,
        persistence="disk",
    )
```

See `examples/client/02_custom_model.md` through `06_full_control.md` for
the full configuration surface.

`Client.standalone()` may take a small number of server-only knobs
(`cwd=`, `agent_dir=`, `log_file=`) but should not duplicate session-level
configuration.

## Comparison to upstream

`pi-mono/packages/coding-agent/src/main.ts` boots the agent in-process:

```typescript
const { session, dispose } = await createAgentSession({
  cwd, model, sessionManager, settingsManager, /* ... */
});
```

No server, no wire, no embedded transport — the CLI process owns the
runtime directly.

In epsilon, the equivalent CLI loop is:

```python
async with Client.standalone(cwd=cwd) as client:
    session = await client.create_session(model=model, ...)
    # drive session
```

Differences:

- runtime ownership moves from the CLI process to an in-process server;
  the CLI is purely a client
- session manager, settings manager, auth storage, model registry all live
  on the server (or behind it); the client sees a flatter config surface
- `dispose()` becomes context-manager exit on both the client and the
  embedded server

The CLI behavior end users see (`epsilon` interactive, print mode, resume,
list, etc.) is unchanged in intent; only the internal wiring differs.

## Open questions

- whether `Client.standalone()` accepts a pre-built `Server` (dependency
  injection) for tests, or always constructs its own; leaning accept-built
  for testability with a default that constructs one
- whether the embedded server runs in a worker task on the same event loop
  or in a dedicated thread / subprocess; same-loop is simpler and should be
  fine for the standalone case
- crash handling: if the embedded server task dies, surface it on the next
  client call vs raise immediately on the active `session.events()`
  iterator; leaning raise-on-iterator so streaming consumers notice
- log routing: embedded server logs to stderr by default, configurable via
  `log_file=`; matches upstream behavior
