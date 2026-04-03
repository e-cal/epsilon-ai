from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable
from typing import Any


class RequestAbortedError(RuntimeError):
    pass


async def maybe_await[T](value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


def is_signal_aborted(signal: Any | None) -> bool:
    if signal is None:
        return False

    aborted = getattr(signal, "aborted", None)
    if isinstance(aborted, bool):
        return aborted

    is_set = getattr(signal, "is_set", None)
    if callable(is_set):
        try:
            return bool(is_set())
        except TypeError:
            return False

    return False


def raise_if_signal_aborted(signal: Any | None) -> None:
    if is_signal_aborted(signal):
        raise RequestAbortedError("Request was aborted")


def create_abort_task(signal: Any | None) -> asyncio.Task[object] | None:
    if signal is None:
        return None

    wait = getattr(signal, "wait", None)
    if not callable(wait):
        return None

    waiter = wait()
    if not inspect.isawaitable(waiter):
        return None

    return asyncio.create_task(_await_waiter(waiter))


async def _await_waiter(waiter: Awaitable[Any]) -> object:
    return await waiter
