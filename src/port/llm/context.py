"""Per-review runtime context: progress callback and cooperative stop signal.

These are contextvars rather than arguments because they cross the LangGraph
node boundary, where the graph controls the call signature.
"""

from __future__ import annotations

import contextvars
import threading

step_callback: contextvars.ContextVar = contextvars.ContextVar("step_callback", default=None)
review_stop_event: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "review_stop_event", default=None
)
class ReviewStoppedError(RuntimeError):
    pass
class StructuredLLMOutputError(RuntimeError):
    def __init__(self, *, agent: str, schema_name: str):
        self.agent = agent
        self.schema_name = schema_name
        super().__init__(
            f"{agent.title()} agent returned malformed structured output after retries. "
            "The model produced invalid JSON, so the review could not continue. "
            "Retry the review, or choose a stronger model for this agent."
        )
def raise_if_review_stopped() -> None:
    event = review_stop_event.get()
    if event is not None and event.is_set():
        raise ReviewStoppedError("Review stopped by user.")
