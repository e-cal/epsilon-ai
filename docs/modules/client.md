# `epsilon.client`

Async Python client for `epsilon.server`.

## Purpose

The canonical consumer surface for the coding agent. `epsilon.tui` is built on top of this client, and external Python integrations of the coding agent are expected to use it as well.

## Why it exists

- keeps `epsilon.server` as the single sanctioned consumption point for the harness
- avoids forcing TUI and external integrations to re-implement transport handling, event parsing, reconnection, and session-state tracking
- preserves a clean separation: the harness exposes primitives, the server exposes a wire API, the client exposes an ergonomic Python API over that wire API

## Current status

Scaffolding only. The endpoint surface it wraps is itself still TBD; see `docs/modules/server.md`.

## Planned scope

- 1:1 method surface mapping `epsilon.server` endpoints
- mirror the server's streaming and event semantics; do not re-implement the harness loop client-side
- propagate event types and ordering as-is from the server (which in turn matches `epsilon.harness`)
- optional sync wrappers around the async API for callers that are not async-native

## Open design questions

- sync wrapper strategy: blocking helpers via `asyncio.run`, a dedicated thread-backed adapter, or a separate sync client module
- reconnection and event replay: whether the client transparently resumes streams or surfaces gaps to the caller
- standalone-mode lifecycle: whether the client owns the embedded local server process in standalone use, or a separate launcher is responsible for spawning and tearing down the server

## Reference

- planned source location: `epsilon/client/`
- see `docs/modules/server.md` for the wire API being wrapped
- see `docs/modules/tui.md` for the primary in-tree consumer
