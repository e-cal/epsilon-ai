from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..runtime import RequestAbortedError, create_abort_task, raise_if_signal_aborted


async def iterate_sse_messages(
    response: httpx.Response,
    signal: Any | None = None,
) -> AsyncIterator[tuple[str | None, str]]:
    event_name: str | None = None
    data_lines: list[str] = []
    iterator = response.aiter_lines()
    abort_task = create_abort_task(signal)

    try:
        while True:
            raise_if_signal_aborted(signal)
            try:
                line = await _next_line(iterator, abort_task)
            except StopAsyncIteration:
                break

            if line == "":
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                event_name = None
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]

            if field == "event":
                event_name = value or None
            elif field == "data":
                data_lines.append(value)

        if data_lines:
            yield event_name, "\n".join(data_lines)
    finally:
        if abort_task is not None:
            abort_task.cancel()
            await asyncio.gather(abort_task, return_exceptions=True)


async def _next_line(
    iterator: AsyncIterator[str],
    abort_task: asyncio.Task[object] | None,
) -> str:
    line_task = asyncio.create_task(_next_iterator_line(iterator))
    if abort_task is None:
        return await line_task

    done, _pending = await asyncio.wait(
        {line_task, abort_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if abort_task in done:
        line_task.cancel()
        await asyncio.gather(line_task, return_exceptions=True)
        raise RequestAbortedError("Request was aborted")
    return await line_task


async def _next_iterator_line(iterator: AsyncIterator[str]) -> str:
    return await iterator.__anext__()
