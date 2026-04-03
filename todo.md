# epsilon port todo

## 0. Project framing
- [x] Define target repository/package layout mirroring the upstream monorepo where practical
  - [x] `packages/ai`
  - [x] `packages/agent`
  - [x] `packages/coding-agent`
  - [x] `packages/tui`
- [x] Decide Python workspace/build tooling
  - [x] packaging strategy for multiple internal packages via `uv` workspace members under `packages/*`
  - [x] linting/formatting (`ruff`)
  - [x] type checking (`pyright`, standard mode)
  - [x] testing (`pytest`)
- [ ] Establish coding conventions for parity-focused ports
  - [x] naming conventions between TS and Python
  - [x] async/event-stream conventions
  - [ ] schema/validation strategy

## 1. Upstream analysis and mapping
- [ ] Inventory the upstream `pi-mono` packages and decide what is in scope
  - [x] `ai`
  - [x] `agent`
  - [x] `coding-agent`
  - [x] `tui`
  - [-] explicitly defer `mom`
  - [-] explicitly defer `pods`
  - [-] explicitly defer `web-ui`
- [ ] Produce a source-to-port map for major modules
  - [ ] `packages/ai/src`
  - [ ] `packages/agent/src`
  - [ ] `packages/coding-agent/src`
  - [ ] `packages/tui/src`
- [ ] Identify public APIs and user-visible behavior that must remain compatible
- [ ] Identify test suites upstream that can guide parity validation

## 2. Shared foundations
- [ ] Define shared core data models used across packages
  - [ ] messages/content blocks
  - [ ] tool calls and tool results
  - [ ] usage/cost accounting
  - [ ] models/providers/apis
  - [ ] session records
  - [ ] settings/config models
- [ ] Define serialization formats
  - [ ] conversation context JSON compatibility
  - [ ] session JSONL compatibility where practical
- [ ] Define common utilities
  - [ ] async stream helpers
  - [ ] cancellation/abort semantics
  - [ ] file/path helpers
  - [ ] event emitter/subscriber primitives

## 3. `packages/ai` - AI router / provider layer
### 3.1 Core model and registry layer
- [x] Port provider/model registry concepts
- [x] Port model metadata structures
- [x] Port provider discovery and lookup APIs
- [ ] Port environment-variable credential lookup
- [ ] Port custom model/provider configuration behavior

### 3.2 Message/context normalization
- [ ] Port context/message types
- [ ] Port cross-provider message transformation rules
- [ ] Port thinking/reasoning block handling
- [ ] Port image input and image tool result handling
- [ ] Port tool schema/argument validation behavior

### 3.3 Streaming/completion APIs
- [x] Port unified stream API
- [x] Port unified complete API
- [x] Port simplified stream/complete APIs
- [~] Port event model
  - [ ] start
  - [ ] text start/delta/end
  - [ ] thinking start/delta/end
  - [ ] toolcall start/delta/end
  - [ ] done
  - [ ] error
- [ ] Port abort/error continuation semantics

### 3.4 Providers
- [ ] Inventory upstream providers and prioritize implementation order
- [x] Implement a faux/fake provider for tests first
- [ ] Implement core real providers needed for the coding agent first
  - [ ] Anthropic
  - [ ] OpenAI
  - [ ] Google
  - [ ] OpenAI-compatible providers abstraction
- [ ] Add secondary providers after the main abstraction is stable
- [ ] Port OAuth/subscription-based provider support where needed for parity

### 3.5 Tests
- [ ] Port/replicate parity tests for streaming behavior
- [ ] Port/replicate token and usage tests
- [ ] Port/replicate abort/error tests
- [ ] Port/replicate cross-provider handoff tests
- [ ] Port/replicate image and tool-call edge case tests

## 4. `packages/agent` - agent framework
### 4.1 Core state and types
- [ ] Port agent state model
- [ ] Port agent message model including extensibility strategy
- [ ] Port agent events and event ordering guarantees
- [ ] Port thinking/tool execution settings

### 4.2 Agent loop
- [ ] Port `prompt()` semantics
- [ ] Port `continue()` semantics
- [ ] Port low-level loop APIs
- [ ] Port tool execution pipeline
  - [ ] validation
  - [ ] before-tool hook
  - [ ] execution
  - [ ] streaming updates
  - [ ] after-tool hook
  - [ ] tool result message emission
- [ ] Port sequential vs parallel tool execution behavior

### 4.3 Queueing and control flow
- [ ] Port steering queue
- [ ] Port follow-up queue
- [ ] Port clear queue operations
- [ ] Port abort/wait-for-idle behavior
- [ ] Match upstream barrier semantics around awaited subscribers

### 4.4 Tests
- [ ] Add deterministic event-sequence tests
- [ ] Add tool execution ordering tests
- [ ] Add abort/retry tests
- [ ] Add steering/follow-up behavior tests

## 5. `packages/tui` - terminal UI support
> Planned intentionally last. This is the main area where implementation may deviate from upstream more substantially.

### 5.1 TUI strategy decision
- [ ] Work on TUI only after the core `ai`, `agent`, and `coding-agent` layers are stable enough to drive it
- [ ] Compare candidate directions
  - [ ] follow `pi` closely
  - [ ] custom Python implementation with Textual
  - [ ] follow `~/projects/opencode` / OpenTUI patterns
  - [ ] custom implementation with OpenTUI
- [ ] Current preferred direction: opencode-inspired OpenTUI hybrid
- [ ] Document the final decision and why
- [ ] Optimize for modularity and hackability so the interaction model can evolve

### 5.2 Rendering/runtime primitives
- [ ] Inventory upstream TUI architecture
- [ ] Inventory `~/projects/opencode` architecture and identify reusable design ideas
- [ ] Decide terminal library/runtime strategy
- [ ] Port or redesign enough rendering primitives to support the coding agent
- [ ] Port or redesign input/key event normalization
- [ ] Implement diff/minimal redraw behavior if needed for usability/perf parity

### 5.3 Interaction components needed by coding agent
- [ ] editor/input widget
- [ ] message list rendering
- [ ] footer/status rendering
- [ ] overlays/dialogs/selectors
- [ ] keyboard shortcut handling
- [ ] theme support
- [ ] keep UI modules loosely coupled so pieces can be redesigned independently

### 5.4 Tests/manual validation
- [ ] Add non-flaky rendering/state tests where feasible
- [ ] Establish tmux/manual smoke-test procedure
- [ ] Validate key workflows against upstream behavior even if implementation differs

## 6. `packages/coding-agent` - coding harness / CLI
### 6.1 Core session runtime
- [ ] Port model resolution/default model selection
- [ ] Port session runtime wiring across AI + agent + TUI
- [ ] Port built-in tools
  - [ ] read
  - [ ] write
  - [ ] edit
  - [ ] bash
  - [ ] grep
  - [ ] find
  - [ ] ls
- [ ] Port built-in system prompt and harness behavior

### 6.2 CLI and non-interactive modes
- [ ] Port interactive mode
- [ ] Port print mode
- [ ] Port JSON mode
- [ ] Port RPC mode
- [ ] Port CLI argument parsing and help text

### 6.3 Sessions and persistence
- [ ] Port session file format and storage layout
- [ ] Port resume/new/fork flows
- [ ] Port tree navigation semantics
- [ ] Port export/share behavior as appropriate
- [ ] Port compaction triggers and flow

### 6.4 Configuration and resource loading
- [ ] Port config directory layout
- [ ] Port settings loading/override rules
- [ ] Port `AGENTS.md` / `CLAUDE.md` loading semantics
- [ ] Port `.pi/SYSTEM.md` and append-system behavior
- [ ] Port prompt template loading
- [ ] Port skill loading
- [ ] Port extension architecture or define parity-compatible Python equivalent
- [ ] Port themes

### 6.5 Authentication and model/provider UX
- [ ] Port login/logout flows needed for supported providers
- [ ] Port model selector UX
- [ ] Port scoped model cycling
- [ ] Port thinking-level controls

### 6.6 Tests
- [ ] Add tool harness tests with faux provider
- [ ] Add CLI mode tests
- [ ] Add session persistence tests
- [ ] Add regression tests for built-in tool behavior

## 7. Extensions / skills / prompts parity strategy
- [ ] Decide compatibility target for extensions
  - [ ] full parity
  - [ ] Python-native equivalent
  - [ ] staged deferral with stable architecture boundary
- [ ] Port prompt template behavior
- [ ] Port skills loading and invocation behavior
- [ ] Define whether extension APIs are ported immediately or later

## 8. Documentation
- [ ] Expand root `README.md` with project goals and scope
- [ ] Add package-level READMEs as packages appear
- [ ] Document development workflow and parity strategy
- [ ] Document deliberate deviations from upstream, if any

## 9. Incremental delivery plan
- [~] Milestone 1: repo skeleton + tooling + shared types
- [~] Milestone 2: minimal `ai` with faux provider + stream API
- [ ] Milestone 3: minimal `agent` loop with tools
- [ ] Milestone 4: minimal coding-agent CLI with read/write/edit/bash
- [ ] Milestone 5: interactive TUI usable end-to-end (deferred until after the core runtime is stable; likely OpenTUI-based)
- [ ] Milestone 6: session persistence + compaction + model management
- [ ] Milestone 7: parity hardening via upstream behavior tests and edge cases
