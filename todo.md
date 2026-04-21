# epsilon-ai port todo

## 0. Project framing
- [x] Define target repository/module layout mirroring the upstream monorepo where practical
  - [x] `epsilon.llm`
  - [x] `epsilon.agent`
  - [x] `epsilon.coding_agent`
  - [x] `epsilon.tui`
- [x] Decide Python packaging/build tooling
  - [x] packaging strategy for a single `epsilon-ai` distribution with module divisions
  - [x] linting/formatting (`ruff`)
  - [x] type checking (`pyright`, standard mode)
  - [x] testing (`pytest`)
- [x] Establish coding conventions for parity-focused ports
- [x] naming conventions between TS and Python
- [x] async/event-stream conventions
- [x] schema/validation strategy
  - [x] lightweight JSON Schema-like runtime validation for agent tools
- [x] Reference-repo sync workflow documented in `AGENTS.md`

## 1. Upstream analysis and mapping
- [x] Inventory the upstream `pi-mono` packages and decide what is in scope
  - [x] `ai`
  - [x] `agent`
  - [x] `coding-agent`
  - [x] `tui`
  - [-] explicitly defer `mom`
  - [-] explicitly defer `pods`
  - [-] explicitly defer `web-ui`
- [x] Produce a source-to-port map for major modules
  - [x] `pi-mono/packages/ai/src` -> `epsilon.llm`
  - [x] `pi-mono/packages/agent/src` -> `epsilon.agent`
  - [ ] `pi-mono/packages/coding-agent/src` -> `epsilon.coding_agent`
  - [ ] `pi-mono/packages/tui/src` -> `epsilon.tui`
- [x] Identify public APIs and user-visible behavior that must remain compatible (for in-scope providers and the agent runtime)
- [x] Identify test suites upstream that can guide parity validation

## 2. Shared foundations
- [x] Define shared core data models used across packages
  - [x] messages/content blocks
  - [x] tool calls and tool results
  - [x] usage/cost accounting
  - [x] models/providers/apis
  - [~] session records (partial — covered by the catalog + model registry, not session persistence yet)
  - [~] settings/config models (covered for stream options; full coding-agent settings layer pending)
- [~] Define serialization formats
  - [ ] conversation context JSON compatibility
  - [ ] session JSONL compatibility where practical
- [x] Define common utilities
  - [x] async stream helpers
  - [x] cancellation/abort semantics
  - [~] file/path helpers (minimal; will grow with coding_agent)
  - [x] event emitter/subscriber primitives

## 3. `epsilon.llm` - LLM client / provider layer
### 3.1 Core model and registry layer
- [x] Port provider/model registry concepts
- [x] Port model metadata structures
- [x] Port provider discovery and lookup APIs
- [x] Port environment-variable credential lookup
- [~] Port custom model/provider configuration behavior (registry supports this; compat options partially typed)

### 3.2 Message/context normalization
- [x] Port context/message types
- [x] Port cross-provider message transformation rules
- [x] Port thinking/reasoning block handling
- [x] Port image input and image tool result handling
- [x] Port tool schema/argument validation behavior

### 3.3 Streaming/completion APIs
- [x] Port unified stream API
- [x] Port unified complete API
- [x] Port simplified stream/complete APIs
- [x] Port event model
  - [x] start
  - [x] text start/delta/end
  - [x] thinking start/delta/end
  - [x] toolcall start/delta/end
  - [x] done
  - [x] error
- [x] Port abort/error continuation semantics

### 3.4 Providers
- [x] Inventory upstream providers and prioritize implementation order
- [x] Implement a faux/fake provider for tests first
- [x] Implement core real providers for the selected scope
  - [x] Anthropic
  - [x] OpenAI Responses
  - [x] OpenAI Codex Responses
  - [x] Azure OpenAI Responses
  - [ ] Google (out of current scope)
  - [ ] OpenAI-compatible providers abstraction (out of current scope)
- [ ] Add secondary providers after the main abstraction is stable (out of current scope)
- [~] Port OAuth/subscription-based provider support where needed for parity
  - [x] OpenAI Codex OAuth
  - [ ] Anthropic OAuth
  - [ ] GitHub Copilot OAuth
  - [ ] Google / Gemini CLI OAuth

### 3.5 Tests
- [x] Port/replicate parity tests for streaming behavior (selected providers)
- [x] Port/replicate token and usage tests
- [~] Port/replicate abort/error tests
- [~] Port/replicate cross-provider handoff tests (transform_messages coverage)
- [x] Port/replicate image and tool-call edge case tests

### 3.6 Recent upstream parity sync (tracked in `epsilon/llm/status.md`)
- [x] Tool-call provider sets match upstream
- [x] xhigh gating uses `supports_xhigh`
- [x] `session_id` + `x-client-request-id` headers for OpenAI-compatible Responses
- [x] Opus 4.7 support (xhigh, adaptive thinking, effort mapping)
- [x] Anthropic `thinking_display` with summarized default
- [x] Anthropic tools cache control separation
- [x] OpenAI Codex service-tier support and resolver

## 4. `epsilon.agent` - agent framework
### 4.1 Core state and types
- [x] Port agent state model
- [~] Port agent message model including extensibility strategy (custom messages require user-side documentation)
- [x] Port agent events and event ordering guarantees
- [x] Port thinking/tool execution settings

### 4.2 Agent loop
- [x] Port `prompt()` semantics
- [x] Port `continue()` semantics (exposed as `continue_()` in Python)
- [x] Port low-level loop APIs
- [x] Port tool execution pipeline
  - [x] validation
  - [x] before-tool hook
  - [x] execution
  - [x] streaming updates
  - [x] after-tool hook (with finalization error guard; upstream b9cd557d)
  - [x] tool result message emission
- [x] Port sequential vs parallel tool execution behavior

### 4.3 Queueing and control flow
- [x] Port steering queue
- [x] Port follow-up queue
- [x] Port clear queue operations
- [x] Port abort/wait-for-idle behavior
- [x] Match upstream barrier semantics around awaited subscribers

### 4.4 Tests
- [~] Add deterministic event-sequence tests
- [x] Add tool execution ordering tests
- [~] Add abort/retry tests
- [x] Add steering/follow-up behavior tests

## 5. `epsilon.coding_agent` - coding harness / CLI (NEXT MILESTONE)
### 5.1 Package scaffolding (immediate next step)
- [ ] Create module layout mirroring upstream `packages/coding-agent/src/`
  - [ ] `epsilon/coding_agent/core/` — session runtime, model resolution, system prompt loading
  - [ ] `epsilon/coding_agent/tools/` — built-in tools
  - [ ] `epsilon/coding_agent/cli/` — CLI entry points (start with print mode)
- [ ] Port/adapt the upstream system prompt
- [ ] Wire an `Agent` from `epsilon.agent` with a default model and `convert_to_llm`
- [ ] Implement a minimum viable `print` CLI mode that runs one prompt end to end
- [ ] Add faux-provider integration tests that drive the harness from a prompt through tool execution

### 5.2 Built-in tools
- [ ] `read`
- [ ] `write`
- [ ] `edit`
- [ ] `bash`
- [ ] `grep`
- [ ] `find`
- [ ] `ls`
- [ ] regression tests per tool using the faux provider

### 5.3 CLI and non-interactive modes
- [ ] Port print mode (first)
- [ ] Port JSON mode
- [ ] Port RPC mode
- [ ] Port interactive mode (waits for TUI)
- [ ] Port CLI argument parsing and help text

### 5.4 Sessions and persistence
- [ ] Port session file format and storage layout
- [ ] Port resume/new/fork flows
- [ ] Port tree navigation semantics
- [ ] Port export/share behavior as appropriate
- [ ] Port compaction triggers and flow (requires `utils/overflow.ts` port)

### 5.5 Configuration and resource loading
- [ ] Port config directory layout
- [ ] Port settings loading/override rules
- [ ] Port `AGENTS.md` / `CLAUDE.md` loading semantics
- [ ] Port `.pi/SYSTEM.md` and append-system behavior
- [ ] Port prompt template loading
- [ ] Port skill loading
- [ ] Port extension architecture or define parity-compatible Python equivalent
- [ ] Port themes

### 5.6 Authentication and model/provider UX
- [ ] Port login/logout flows needed for supported providers
- [ ] Port model selector UX
- [ ] Port scoped model cycling
- [ ] Port thinking-level controls

## 6. `epsilon.tui` - terminal UI support (DEFERRED)
> Planned intentionally last. This is the main area where implementation may deviate from upstream more substantially. Work starts after the coding-agent scaffolding is usable end to end in a non-interactive CLI mode.

### 6.1 TUI strategy decision
- [ ] Compare candidate directions
  - [ ] follow `pi` closely
  - [ ] custom Python implementation with Textual
  - [ ] follow `~/projects/opencode` / OpenTUI patterns
  - [ ] custom implementation with OpenTUI
- [ ] Current preferred direction: opencode-inspired OpenTUI hybrid
- [ ] Document the final decision and why
- [ ] Optimize for modularity and hackability so the interaction model can evolve

### 6.2 Rendering/runtime primitives
- [ ] Inventory upstream TUI architecture
- [ ] Inventory `~/projects/opencode` architecture and identify reusable design ideas
- [ ] Decide terminal library/runtime strategy
- [ ] Port or redesign enough rendering primitives to support the coding agent
- [ ] Port or redesign input/key event normalization
- [ ] Implement diff/minimal redraw behavior if needed for usability/perf parity

### 6.3 Interaction components needed by coding agent
- [ ] editor/input widget
- [ ] message list rendering
- [ ] footer/status rendering
- [ ] overlays/dialogs/selectors
- [ ] keyboard shortcut handling
- [ ] theme support
- [ ] keep UI modules loosely coupled so pieces can be redesigned independently

### 6.4 Tests/manual validation
- [ ] Add non-flaky rendering/state tests where feasible
- [ ] Establish tmux/manual smoke-test procedure
- [ ] Validate key workflows against upstream behavior even if implementation differs

## 7. Extensions / skills / prompts parity strategy
- [ ] Decide compatibility target for extensions
  - [ ] full parity
  - [ ] Python-native equivalent
  - [ ] staged deferral with stable architecture boundary
- [ ] Port prompt template behavior
- [ ] Port skills loading and invocation behavior
- [ ] Define whether extension APIs are ported immediately or later

## 8. Documentation
- [x] Root `README.md` reflects current module status
- [x] Module docs reflect current module status (`docs/modules/*.md`)
- [x] Module-level status files under `epsilon/<module>/status.md` for llm and agent
- [ ] Add package-level READMEs as packages appear
- [~] Document development workflow and parity strategy (`AGENTS.md`)
- [ ] Document deliberate deviations from upstream, if any

## 9. Incremental delivery plan
- [x] Milestone 1: repo skeleton + tooling + shared types
- [x] Milestone 2: minimal `ai` with faux provider + stream API
- [x] Milestone 3: minimal `agent` loop with tools
- [ ] Milestone 4: minimal coding-agent CLI with read/write/edit/bash (next)
- [ ] Milestone 5: interactive TUI usable end-to-end (deferred until after the core runtime is stable; likely OpenTUI-based)
- [ ] Milestone 6: session persistence + compaction + model management
- [ ] Milestone 7: parity hardening via upstream behavior tests and edge cases
