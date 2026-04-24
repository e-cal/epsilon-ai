# `epsilon.coding_agent`

Epsilon AI Framework module corresponding to the upstream `pi-mono/packages/coding-agent` package.

Current status: package scaffolding only.

## Intended Deviations

- The long-term goal is behavior parity with `pi-mono/packages/coding-agent`, but the Python package layout and internal composition may diverge where that produces a cleaner fit with `epsilon.agent`, `epsilon.llm`, and Python CLI conventions
- Interactive/TUI-facing pieces are expected to diverge more than the core harness logic

No concrete user-facing deviations are locked in yet beyond those structural expectations.

## Next step: scaffolding

The next milestone is to stand up the package with a minimum viable harness so it can drive the already-ported `epsilon.llm` and `epsilon.agent` layers.

Initial scaffolding targets:

- Package layout mirroring upstream `packages/coding-agent/src/` where practical
  - `epsilon/coding_agent/core/` — session runtime, model resolution, system prompt
  - `epsilon/coding_agent/tools/` — built-in tools
  - `epsilon/coding_agent/cli/` — CLI modes (print first, then interactive stub)
- Faithful port of the upstream system prompt and harness wiring
- Minimum viable tool set: `read`, `write`, `edit`, `bash`, `grep`, `find`, `ls`
  - Each tool gets a JSON-Schema-like `parameters` dict and an async `execute` function using the `AgentTool` interface
- Non-interactive "print" CLI mode that wires an `Agent` + faux or real provider to stdout
- Faux-provider-driven regression tests for the harness and each tool

Deferred until after scaffolding lands:

- Interactive mode (waits for TUI work)
- JSON / RPC CLI modes
- Sessions, persistence, resume/fork/compaction
- Config directory layout, `AGENTS.md` / `CLAUDE.md` loading, `.pi/SYSTEM.md`
- Prompt templates, skills, extensions, themes
- Login/logout flows beyond what `epsilon.llm.oauth` already supports

## Planned scope (full)

- coding harness and session runtime
- built-in tools (`read`, `write`, `edit`, `bash`, `grep`, `find`, `ls`)
- CLI modes (print, interactive, JSON, RPC)
- sessions, config loading, and project context files
