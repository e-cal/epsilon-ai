# `epsilon.llm` status

## Summary

- Provider/router port is implemented and tested.
- Parity sync against upstream pi-mono is current as of commit `ddbf6421` (2026-04-17).
- Providers in scope: OpenAI Responses, OpenAI Codex Responses, Azure OpenAI Responses, Anthropic Messages, faux.

## Implemented

- `epsilon.llm.types` core types (messages, content blocks, tools, usage, events, options)
- `epsilon.llm.event_stream` generic event stream + `AssistantMessageEventStream`
- `epsilon.llm.stream` unified `stream` / `complete` / `stream_simple` / `complete_simple`
- `epsilon.llm.api_registry` provider registry
- `epsilon.llm.models` model registry with `get_model`, `get_models`, `get_providers`, `calculate_cost`, `supports_xhigh`, `models_are_equal`
- `epsilon.llm.model_catalog` auto-generated catalog of upstream-relevant models via `scripts/generate_model_catalog.py`
- `epsilon.llm.env_api_keys` env-var API key lookup
- `epsilon.llm.oauth` OAuth flow for OpenAI Codex only
- `epsilon.llm.providers.openai_responses` + `.openai_responses_shared`
- `epsilon.llm.providers.openai_codex_responses`
- `epsilon.llm.providers.azure_openai_responses`
- `epsilon.llm.providers.anthropic`
- `epsilon.llm.providers.faux`
- `epsilon.llm.providers.transform_messages` with synthetic tool-result insertion for orphaned tool calls
- deterministic parity tests under `tests/llm/`

## Behavior covered now

- streaming assistant events with upstream event type strings preserved
- tool calling including cross-provider tool-call id normalization
- reasoning / thinking controls per-provider (including Anthropic adaptive thinking, `thinking_display`, OpenAI Responses reasoning effort/summary, Codex reasoning effort/summary/text verbosity/service tier)
- cost calculation including OpenAI Responses + Codex service-tier multipliers
- prompt cache hints (session_id + `x-client-request-id` headers for OpenAI-compatible Responses, `prompt_cache_key` payload field, retention mode)
- OAuth token-based auth for OpenAI Codex Responses
- abort/error plumbing through `signal` → error `AssistantMessage` with `stopReason`

## Recent upstream parity sync (pi-mono)

- `OPENAI_TOOL_CALL_PROVIDERS` / `AZURE_TOOL_CALL_PROVIDERS` sets match upstream
- `stream_simple_openai_responses` / `stream_simple_azure_openai_responses` gate xhigh via `supports_xhigh(model)`
- `session_id` + `x-client-request-id` headers set for all openai-responses calls when `session_id` present and cache retention != `"none"` (pi-mono 45f1a2cd, 018b40c3)
- Codex Responses also sets `x-client-request-id` alongside `session_id`
- `Opus 4.7` support: included in `supports_xhigh`, adaptive thinking, and the effort-level mapping (pi-mono d1c6cb1e)
- `AnthropicEffort` extended with `"xhigh"`
- `AnthropicThinkingDisplay` added; adaptive/enabled thinking payloads carry a `display` field (default `"summarized"`) (pi-mono acbf8eca)
- Anthropic tool cache control attached to the last tool entry, separate from transcript cache control (pi-mono 1c016cb0)
- Codex `service_tier` option, payload propagation, pricing multiplier, and "trust requested tier" resolver (pi-mono f829f808, 2cdac738)

## Gaps / next work (before coding_agent scaffolding completes)

- OAuth flows for Anthropic, GitHub Copilot, Google, Gemini CLI not ported (out of current scope)
- `utils/overflow.ts` and `utils/typebox-helpers.ts` not ported (overflow is needed for coding-agent compaction)
- Built-in provider registration is eager; upstream uses lazy import wrappers
- e2b40dfc (strip `partialJson` on finalize/error) is N/A: the port never persists streaming scratch state on tool-call blocks, so there is nothing to strip

## Work log

- 2026-04-03: initial port of LLM types, event stream, provider router, OpenAI/Azure/Anthropic/Codex providers, faux provider, oauth for codex, tests
- 2026-04-06: model catalog generator script landed
- 2026-04-16: reviewed upstream diffs since 2026-04-03; applied tool-call provider set, xhigh gate, session_id header, Opus 4.7, thinking display, tools cache separation, and codex service tier fixes; regenerated the model catalog
