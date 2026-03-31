"""Risk agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import make_llm
from port.models import RiskReview
from port.prompts import RISK_SYSTEM_PROMPT
from port.state import GraphState


def risk_node(state: GraphState) -> dict:
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(RiskReview)
    content = build_analysis_prompt(state)

    result: RiskReview = structured_llm.invoke([
        SystemMessage(content=RISK_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"risk_results": [result]}
