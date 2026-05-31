# `epsilon.server` examples

Status: **not yet built**. Module is scaffolding only.

These sketches are **work-backward design specs** for the wire API. Treat
them as the canonical shape the server should land at, not as runnable
code. When `epsilon.server` is implemented, sketches that no longer match
the API will be ported to runnable `.py`.

| File | Shows |
|------|-------|
| `01_launch_local_server.md` | embedding a local server in a Python process |
| `02_wire_protocol.md` | session lifecycle over the wire (events, framing) |

## Architectural note

`epsilon.server` hosts an `epsilon.harness.Agent` runtime and exposes it as
a wire API. The coding-agent is server-first: even standalone single-user
invocations run a local server. This deviates intentionally from
`pi-mono/packages/coding-agent`, which is consumed in-process via
`createAgentSession()`. See `docs/modules/server.md`.

Categories the wire API must cover (verbatim from `docs/modules/server.md`):

- session lifecycle: create, list, resume, fork, dispose
- prompts / messages: send user prompt, stream events
- steering and follow-up queues
- abort and wait-for-idle
- tool execution control: before/after-tool hook surface, allow/deny,
  mode override (sequential vs parallel)
- config: model selection, reasoning level, tool allowlist, paths and
  context files (`AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`)
- introspection: current state, queued items, recent events

Event semantics must mirror `epsilon.harness` event types and ordering. The
server is a transport over the harness, not a re-implementation.

## Open design questions (still TBD)

- transport choice: HTTP + SSE, WebSocket, or both
- authn / authz model for non-local use (local-only assumes loopback trust)
- single session per process vs multi-session per process
- streaming protocol framing, backpressure, replay semantics
- session persistence ownership: server-owned vs harness-owned vs separate
  storage-layer module
- how the in-process standalone server is launched, addressed, and torn
  down (see `examples/standalone/`)
