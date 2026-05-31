# `standalone` examples

Status: **design sketches**. The pieces this stitches together
(`epsilon.server`, `epsilon.client`) are scaffolding only.

These sketches show how the **server-first coding agent** runs as a single
local process — the canonical way an end user, a script, or the TUI invokes
the coding agent without standing up a separate server.

This directory has no upstream equivalent. `pi-mono/packages/coding-agent`
exposes an in-process API (`createAgentSession()`) that callers drive
directly. epsilon does not: even the standalone single-user invocation runs
through `epsilon.server` and is consumed by `epsilon.client`.

## Why server-first standalone

- one consumption surface (`epsilon.client`) covers standalone, hosted, and
  remote use; the TUI and external Python integrations do not branch
- session state, persistence, tool execution, and event ordering live on
  the server in every mode; nothing is reimplemented client-side
- the wire API is exercised in every invocation, so it cannot silently rot
- there is no in-process bypass to test against, which keeps the
  client / server contract honest

The cost is one extra hop on localhost. For a coding-agent workload that is
negligible compared to LLM round-trips.

## Files

| File | Shows |
|------|-------|
| `01_standalone_coding_agent.md` | embedded server + client in a single process, owned by the client |

Future sketches likely to live here once the surface stabilizes:

- launching `epsilon serve` as a separate process and connecting a client
  to it
- the canonical CLI entrypoint shape (`python -m epsilon` / `epsilon`),
  modeled on `pi-mono/packages/coding-agent/src/main.ts` but stripped of
  the in-process path

## Open questions

- ownership of the embedded server: `Client.standalone()` spawns and tears
  it down, vs a separate `epsilon.standalone.launch()` helper that returns
  a `(server, client)` pair. Leaning client-owned for ergonomic single-call
  use, with the lower-level launcher available for advanced cases.
- whether `Client.standalone()` reuses an existing local server if one is
  already running on a well-known port, or always spawns a fresh one.
  Leaning always-spawn for predictability.
- standalone CLI surface: which `pi-mono/packages/coding-agent` CLI flags
  (model, thinking, tool allowlist, session resume, print mode) carry over
  1:1 vs need adaptation for the server-first model.

## Reference

- `docs/modules/server.md` — server-first principle
- `docs/modules/client.md` — canonical consumer
- `examples/server/01_launch_local_server.md` — embedded server lifecycle
- `examples/client/01_minimal.md` — client-side minimal usage
- `pi-mono/packages/coding-agent/src/main.ts` — upstream CLI entry, reference only
