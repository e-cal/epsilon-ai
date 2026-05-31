# `epsilon.tui`

Terminal UI for the coding agent.

## Architectural direction

OpenTUI-based, modeled on `~/projects/opencode`'s TUI architecture. This is an intentional deviation from `pi-mono/packages/tui`.

Modularity and hackability matter more than upstream structural parity here. Equivalent end-user capabilities in the coding agent are the bar, not 1:1 component-level parity with upstream.

## Consumption boundary

`epsilon.tui` consumes `epsilon.client`. It does not talk to `epsilon.harness` directly, and it does not embed the server. Standalone-mode server lifecycle is handled at the client layer or by a dedicated launcher; the TUI sees only the client API.

See `docs/modules/client.md` and `docs/modules/server.md`.

## Current status

Scaffolding only. Work is deferred until `epsilon.server`, `epsilon.client`, and the coding-tool / system-prompt / session pieces of `epsilon.harness` are usable end-to-end.

## Planned scope

- terminal rendering and runtime primitives, OpenTUI-based
- reusable UI components needed by the coding agent
- theme support
- OpenTUI-aligned component architecture, modeled on `~/projects/opencode`'s TUI
- a modular implementation that can diverge from upstream where helpful
