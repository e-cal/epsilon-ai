# Sketch: launch a local `epsilon.server`

Status: **design sketch**. Names below are proposals.

## Goal

Start a local server bound to loopback, host a single `epsilon.harness.Agent`
runtime per session, and tear it down cleanly. This is the in-process
standalone path that `examples/standalone/` and `epsilon.tui` will use.

## Proposed surface

```python
from epsilon.server import Server, ServerConfig

config = ServerConfig(
    host="127.0.0.1",
    port=0,                       # 0 = pick an ephemeral port
    cwd="/path/to/project",       # default os.getcwd()
    agent_dir="~/.epsilon/agent", # default
    # transport choice still TBD; HTTP+SSE or WebSocket
)

async with Server.serve(config) as server:
    print(f"listening on {server.address}")   # e.g. ("127.0.0.1", 54321)
    await server.until_shutdown()             # blocks until SIGINT or shutdown()
```

`Server.serve()` is an async context manager. On exit it disposes all
sessions, drains in-flight events, and closes the listener.

## Lifecycle

```
Server.serve(config)
├── bind listener (host:port)
├── register harness factory (Agent + tool loader)
├── accept connections
│   ├── session create
│   │   ├── load AGENTS.md / CLAUDE.md / .epsilon/SYSTEM.md
│   │   ├── resolve model + reasoning level
│   │   ├── attach allowed tools
│   │   └── construct Agent
│   ├── prompt / steer / follow-up / abort
│   ├── stream AgentEvent over the wire
│   └── dispose session
└── shutdown
    ├── abort active runs
    ├── await wait_for_idle on each session
    └── close transport
```

## Embedded vs standalone

The same `Server` is used in two ways:

- **embedded** (the standalone path): an `epsilon.client.Client` constructs
  a `Server` against an ephemeral port inside the same process and connects
  to it over loopback. The client owns the server lifetime.
- **standalone process**: a future `epsilon serve` CLI binds a fixed port
  and stays up across multiple client connections.

Either way, the wire API is identical. The client does not branch on which
mode it is in.

## Open questions

- transport: HTTP + SSE for events vs WebSocket; HTTP + SSE is the leading
  candidate because it composes better with reverse proxies and matches
  upstream's RPC framing intuition
- session persistence: server-owned (server picks the on-disk session
  format) vs harness-owned (server is purely a transport over harness, and
  sessions are a harness concern); leaning server-owned because session
  resume must work across server restarts and across embedded vs hosted
  modes
- authn: loopback-trust for embedded, opaque bearer token for hosted; out
  of scope until hosted mode is built
- in-process bypass: explicitly **not** supported; even unit tests of the
  client go through the wire
