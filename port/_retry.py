"""Shared retry-with-backoff helper used by every external-I/O site in ``port``.

The behavioral parameters (``attempts``, ``base``, ``cap``) are required — callers must
specify the retry policy from config explicitly. The structural defaults (sleep impl,
exception classes) keep stable library-wide defaults.
"""

from __future__ import annotations

import time
from collections.abc import Callable


def backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """Exponential backoff for a 1-based attempt number, capped at ``cap``."""
    if base <= 0:
        return 0.0
    return min(base * (2 ** max(0, attempt - 1)), cap)


def with_retry[T](
    fn: Callable[[], T],
    *,
    attempts: int,
    base: float,
    cap: float,
    on_attempt: Callable[[int, Exception, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    retry_on: type[Exception] | tuple[type[Exception], ...] = Exception,
    stop_on: type[BaseException] | tuple[type[BaseException], ...] = (),
) -> T:
    """Call ``fn`` with exponential backoff between failures.

    ``stop_on`` exceptions propagate immediately without sleeping or retrying.
    ``retry_on`` exceptions are retried until ``attempts`` is exhausted, then re-raised.
    ``on_attempt(attempt, exc, delay)`` runs after each failure that will be retried.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except stop_on:
            raise
        except retry_on as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            delay = backoff_seconds(attempt, base=base, cap=cap)
            if on_attempt is not None:
                on_attempt(attempt, exc, delay)
            sleep(delay)
    if last_exc is None:
        raise RuntimeError("with_retry exhausted attempts without success or exception")
    raise last_exc
