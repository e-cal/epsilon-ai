# `epsilon.server`

Hosts an `epsilon.harness.Agent` runtime and exposes it as a wire API.

## Server-first principle

All coding-agent usage goes through the server, including standalone single-user invocations. Standalone use spins up the server in-process; there is no in-process harness code path for the coding-agent CLI or for external Python integrations.

This is an intentional architectural deviation from `pi-mono/packages/coding-agent`, which is consumed in-process. The motivation is to keep a single, stable consumption surface (the wire API) that the TUI, external integrations, and future remote deployments can share without each one re-implementing harness wiring.

Library callers that want to drive the agent runtime directly from Python can still use the primitives in `epsilon.harness`. The coding-agent itself does not have that path.

## Current status

Scaffolding only. Endpoint surface and transport are not yet designed.

## Planned endpoint surface

To be designed. Categories the surface needs to cover:

- session lifecycle: create, list, resume, fork, dispose
- prompts / messages: send user prompt, stream events
- steering and follow-up queues
- abort and wait-for-idle
- tool execution control: before/after-tool hook surface, allow/deny, mode override (sequential vs parallel)
- config: model selection, reasoning level, tool allowlist, paths and context files (`AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`)
- introspection: current state, queued items, recent events

Event semantics must mirror `epsilon.harness` event types and ordering. The server is a transport over the harness, not a re-implementation.

## Open design questions

- transport choice: HTTP + SSE, WebSocket, or both
- authn / authz model for non-local use (local-only assumes loopback trust)
- single session per process vs multi-session per process
- streaming protocol shape: event-per-message framing, backpressure, replay semantics
- session persistence ownership: server-owned vs harness-owned vs storage-layer module
- how the in-process standalone server is launched, addressed, and torn down

## Reference

- planned source location: `epsilon/server/`
- `pi-mono` does not have an exact equivalent; design from scratch, mirror upstream where helpful
- see `docs/modules/harness.md` for the runtime being hosted and `docs/modules/client.md` for the canonical consumer
