from __future__ import annotations

import contextvars
import threading

step_callback: contextvars.ContextVar = contextvars.ContextVar("step_callback", default=None)
review_stop_event: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "review_stop_event", default=None
)


def report_step(agent: str, step_index: int, label: str) -> None:
    """Forward a progress step to the active review's callback, if one is set."""
    callback = step_callback.get()
    if callback is not None:
        callback(agent, step_index, label)


class ReviewStoppedError(RuntimeError):
    pass


def raise_if_review_stopped() -> None:
    event = review_stop_event.get()
    if event is not None and event.is_set():
        raise ReviewStoppedError("Review stopped by user.")
