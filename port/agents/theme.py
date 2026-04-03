"""Theme agent — parallel, runs after news agent."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import make_llm, step_callback as _step_cb
from port.models import ThemeReview
from port.prompts import THEME_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState

log = logging.getLogger(__name__)


def theme_node(state: GraphState) -> dict:
    t0 = time.monotonic()
    log.info("started")
    structured_llm = make_llm(max_tokens=4096, agent="theme").with_structured_output(ThemeReview)
    content = build_analysis_prompt(state)

    _cb = _step_cb.get(None)
    if _cb:
        _cb("theme", 0, "Identifying market themes…")

    result: ThemeReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=THEME_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ]
    )
    log.info("done in %.1fs", time.monotonic() - t0)
    return {"theme_results": [result]}
