"""Epsilon AI Framework client module.

The client is the canonical wire-level consumer of `epsilon.server`.
`epsilon.tui` is built on top of it, and any external integration is
expected to use the client rather than reach into `epsilon.harness`
directly.

See `docs/modules/client.md` for the endpoint surface plan.

This package is currently scaffolding only.
"""
