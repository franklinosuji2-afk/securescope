"""Small in-memory sliding-window rate limiter (per process).

Good enough for a single-instance deployment. For multiple instances use a shared store
(Redis) or an API gateway; see docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 3600.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] >= self.window:
            events.popleft()
        if not events:
            self._events.pop(key, None)
            return self._events[key]
        return events

    def check(self, key: str) -> bool:
        """True if a new event is allowed (does not record it)."""
        return len(self._trim(key, time.monotonic())) < self.limit

    def record(self, key: str) -> None:
        self._events[key].append(time.monotonic())
