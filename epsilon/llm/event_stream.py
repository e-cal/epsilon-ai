from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable

from .types import AssistantMessage, AssistantMessageEvent


class EventStream[TEvent, TResult]:
    def __init__(
        self,
        *,
        is_complete: Callable[[TEvent], bool],
        extract_result: Callable[[TEvent], TResult],
    ) -> None:
        self._is_complete = is_complete
        self._extract_result = extract_result
        self._queue: deque[TEvent] = deque()
        self._waiters: deque[asyncio.Future[tuple[bool, TEvent | None]]] = deque()
        self._done = False
        self._result_future: asyncio.Future[TResult] = asyncio.get_event_loop().create_future()

    def push(self, event: TEvent) -> None:
        if self._done:
            return

        if self._is_complete(event):
            self._done = True
            if not self._result_future.done():
                self._result_future.set_result(self._extract_result(event))

        if self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result((False, event))
            return

        self._queue.append(event)

    def end(self, result: TResult | None = None) -> None:
        self._done = True
        if result is not None and not self._result_future.done():
            self._result_future.set_result(result)

        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result((True, None))

    async def result(self) -> TResult:
        return await self._result_future

    def __aiter__(self) -> AsyncIterator[TEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[TEvent]:
        while True:
            if self._queue:
                yield self._queue.popleft()
                continue

            if self._done:
                return

            waiter = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            done, event = await waiter
            if done:
                return
            if event is not None:
                yield event


def _extract_assistant_result(event: AssistantMessageEvent) -> AssistantMessage:
    if event.type == "done":
        return event.message
    if event.type == "error":
        return event.error
    raise ValueError("Unexpected non-terminal event")


class AssistantMessageEventStream(EventStream[AssistantMessageEvent, AssistantMessage]):
    def __init__(self) -> None:
        super().__init__(
            is_complete=lambda event: event.type in {"done", "error"},
            extract_result=_extract_assistant_result,
        )


def create_assistant_message_event_stream() -> AssistantMessageEventStream:
    return AssistantMessageEventStream()
