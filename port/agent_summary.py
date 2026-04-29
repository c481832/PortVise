from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from port.config import invoke_structured
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


def _safe_json(value: Any, *, max_chars: int = 14000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def fallback_agent_summary(agent: str, output: Any) -> AgentTaskSummary:
    payload = output if isinstance(output, dict) else {}
    agent_review = payload.get(f"{agent}_review")
    body = agent_review if isinstance(agent_review, dict) else payload
    if agent == "news" and isinstance(payload.get("news_review"), dict):
        body = payload["news_review"]
    if agent == "manager" and isinstance(payload.get("manager_review"), dict):
        body = payload["manager_review"]

    summary = ""
    bullets: list[str] = []
    if isinstance(body, dict):
        for key in ("summary", "executive_summary", "brief_rationale", "macro_context"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                summary = value.strip()
                break
        for key in (
            "top_risks",
            "key_events",
            "market_themes",
            "fit_notes",
            "concentration_issues",
            "actions",
        ):
            value = body.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        text = item.get("rationale") or item.get("action_type") or item.get("theme")
                    else:
                        text = item
                    if text:
                        bullets.append(str(text).strip())
                    if len(bullets) >= 3:
                        break
            if len(bullets) >= 3:
                break

    if not summary:
        summary = f"{agent.title()} finished and produced structured output."
    if not bullets:
        bullets = ["Open the agent drawer for the full structured output."]

    return AgentTaskSummary(
        title=f"{agent.title()} complete",
        summary=summary[:420],
        bullets=[b[:220] for b in bullets[:3] if b],
    )


def summarize_agent_output(agent: str, output: Any, portfolio: Portfolio) -> AgentTaskSummary:
    try:
        result: AgentTaskSummary = invoke_structured(  # type: ignore[assignment]
            AgentTaskSummary,
            [
                SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
                HumanMessage(
                    content="\n\n".join(
                        [
                            f"AGENT: {agent}",
                            f"PORTFOLIO: {portfolio.name or 'Portfolio'}",
                            f"OUTPUT JSON:\n{_safe_json(output)}",
                        ]
                    )
                ),
            ],
            agent="agent_summary",
            max_tokens=768,
            temperature=0.1,
        )
        if not result.summary.strip():
            return fallback_agent_summary(agent, output)
        return result
    except Exception as exc:
        log.warning("agent summary failed agent=%s: %s", agent, exc)
        return fallback_agent_summary(agent, output)
