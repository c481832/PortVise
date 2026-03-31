"""Theme agent — parallel, runs after news agent."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from port.agents._base import build_analysis_prompt
from port.config import make_llm
from port.models import ThemeReview
from port.prompts import THEME_SYSTEM_PROMPT
from port.state import GraphState


def theme_node(state: GraphState) -> dict:
    llm = make_llm(max_tokens=4096)
    structured_llm = llm.with_structured_output(ThemeReview)
    content = build_analysis_prompt(state)

    result: ThemeReview = structured_llm.invoke([
        SystemMessage(content=THEME_SYSTEM_PROMPT),
        HumanMessage(content=content),
    ])

    return {"theme_results": [result]}
