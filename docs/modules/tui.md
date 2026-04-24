# `epsilon.tui`

Epsilon AI Framework module corresponding to the upstream `pi-mono/packages/tui` package.

Current status: package scaffolding only. Intentionally deferred until after `epsilon.coding_agent` is usable end-to-end in a non-interactive CLI mode.

## Intended Deviations

- This module is explicitly allowed to diverge from `pi-mono/packages/tui` in implementation strategy
- Terminal UI architecture, framework choice, and component structure do not need 1:1 parity as long as the coding-agent workflows and user capabilities are preserved
- Modularity and hackability are preferred over structural parity here

Planned scope:

- terminal rendering/runtime primitives
- reusable UI components needed by the coding agent
- theme support
- a modular implementation that can diverge from upstream where helpful
