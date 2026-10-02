"""Time-ordered 64-bit ids (Snowflake-style): sortable by creation time without coordination between nodes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

EPOCH_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z
WORKER_BITS = 10
SEQ_BITS = 12
MAX_SEQ = (1 << SEQ_BITS) - 1


class IdGenerator:
    """`timestamp_ms << 22 | worker << 12 | sequence`. Ids from one worker are strictly increasing."""

    def __init__(self, worker_id: int, clock: Callable[[], int] | None = None) -> None:
        if not 0 <= worker_id < (1 << WORKER_BITS):
            raise ValueError("worker_id out of range")
        self.worker_id = worker_id
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._last_ms = -1
        self._seq = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            now = max(self._clock(), self._last_ms)  # never go backwards if the wall clock does
            if now == self._last_ms:
                self._seq = (self._seq + 1) & MAX_SEQ
                if self._seq == 0:  # sequence exhausted within this millisecond: borrow the next one
                    now += 1
            else:
                self._seq = 0
            self._last_ms = now
            return ((now - EPOCH_MS) << (WORKER_BITS + SEQ_BITS)) | (self.worker_id << SEQ_BITS) | self._seq


def timestamp_ms(snowflake: int) -> int:
    return (snowflake >> (WORKER_BITS + SEQ_BITS)) + EPOCH_MS
