"""Epsilon AI Framework server module.

The server hosts an `epsilon.harness` runtime and exposes it over a wire
protocol. All Epsilon coding-agent usage (including local/standalone) runs
through the server -- there is no in-process harness API for the coding
agent itself.

See `docs/modules/server.md` for the architectural rationale and the
endpoint surface plan.

This package is currently scaffolding only.
"""
