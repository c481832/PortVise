"""Regime agent — parallel, runs after news agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import make_llm
from port.models import RegimeReview
from port.prompts import REGIME_SYSTEM_PROMPT

if TYPE_CHECKING:
    from port.state import GraphState


def regime_node(state: GraphState) -> dict:
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(RegimeReview)
    content = build_analysis_prompt(state, portfolio_prefix="Portfolio to assess")

    result: RegimeReview = structured_llm.invoke(  # type: ignore[assignment]
        [
            SystemMessage(content=REGIME_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ]
    )

    return {"regime_results": [result]}
