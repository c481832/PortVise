from __future__ import annotations

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


def with_retry[T](
    fn: Callable[[], T],
    *,
    label: str,
    attempts: int,
    delay: float,
    retry_on: type[Exception] | tuple[type[Exception], ...],
    stop_on: type[BaseException] | tuple[type[BaseException], ...] = (),
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts):
        try:
            return fn()
        except stop_on:
            raise
        except retry_on as exc:
            log.warning(
                "%s attempt %d/%d failed (%s) — retrying in %.1fs",
                label,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    return fn()
