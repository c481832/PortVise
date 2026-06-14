from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import config, invoke_structured
from port.models import AgentTaskSummary
from port.portfolio import Portfolio

log = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = """You summarize one completed portfolio-review agent task.

Return a compact AgentTaskSummary JSON object:
- title: short task-completion title, max 8 words.
- summary: one sentence naming the most decision-relevant result.
- bullets: 2-4 short bullets with concrete findings, no generic process narration.

Do not add recommendations unless the agent output contains them. Do not invent facts.
"""


def _safe_json(value: Any, *, max_chars: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def summarize_agent_output(agent: str, output: Any, portfolio: Portfolio) -> AgentTaskSummary:
    """Run the summary LLM. Raises on failure — no degraded fallback."""
    max_chars = config.agent_summary.max_input_chars
    result: AgentTaskSummary = invoke_structured(  # type: ignore[assignment]
        AgentTaskSummary,
        [
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(
                content="\n\n".join(
                    [
                        f"AGENT: {agent}",
                        f"PORTFOLIO: {portfolio.name or 'Portfolio'}",
                        f"OUTPUT JSON:\n{_safe_json(output, max_chars=max_chars)}",
                    ]
                )
            ),
        ],
        agent="agent_summary",
        max_tokens=config.llm.summary_max_tokens,
        temperature=config.llm.summary_temperature,
    )
    if not result.summary.strip():
        raise RuntimeError(f"agent summary for {agent} returned an empty summary string")
    return result
