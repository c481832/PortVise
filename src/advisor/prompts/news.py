"""News agent system prompt and news formatting."""

from __future__ import annotations

from functools import cache

from advisor.config import config
from advisor.schemas.news import NewsReview
from advisor.schemas.planner import NewsFocus


@cache
def news_system_prompt() -> str:
    n = config.prompts.news
    p = config.prompts.planner
    return f"""You are a market intelligence analyst. Return a concise NewsReview JSON.

The user message includes TOOL-GATHERED RESEARCH. Summarize only that retrieved news evidence
through the lens of SEARCH PRIORITIES: portfolio-level goal, each position's entry thesis, and the
planner's {p.portfolio_query_count} macro queries plus one "latest news for {{ticker}}" query per
line. Use those as your primary lens — surface developments that matter for those goals (tickers,
sectors, macro links). Do not treat the portfolio as generic; anchor themes and events to (1) the
portfolio goal and (2) each position goal where relevant. Prefer facts supported by the research
text; do not invent specific dated events, market levels, or indicators that are not reflected
there. Tailor key_events, market_themes, thesis_risks, and macro_context toward the SEARCH
PRIORITIES where recent facts exist; deprioritise generic filler unrelated to those goals.

Fields:
- macro_context: {n.macro_context_sentence_max} sentences max — rates, USD, credit spreads, equity
  vol, central bank posture, tied to the SEARCH PRIORITIES where applicable.
- market_themes: {n.themes_min}-{n.themes_max} short theme labels aligned with those priorities
  (e.g. "AI capex buildout").
- key_events: up to {n.key_events_max} brief strings — notable recent events for tickers/sectors
  that relate to the stated goals and theses.
- thesis_risks: tickers where recent events challenge the position goals / entry thesis.
- summary: 1 sentence.

Be extremely concise. No explanations outside the JSON fields.

FORMAT: Return a NewsReview JSON object exactly matching the schema."""


def news_focus_to_text(focus: NewsFocus) -> str:
    """The planner's search plan: portfolio goal, each position thesis, and the queries run."""
    lines = [
        "=== SEARCH PRIORITIES ===",
        "",
        "PORTFOLIO GOAL:",
        focus.portfolio_goal or "(none stated)",
        "",
        "POSITION GOALS (entry thesis per ticker):",
    ]
    for pg in focus.position_goals:
        g = pg.goal.strip() if pg.goal else ""
        lines.append(f"  • {pg.ticker}: {g or '(no thesis stated)'}")
        lq = (pg.latest_news_query or "").strip()
        if lq:
            lines.append(f"      → planned query: {lq}")
    pq = [q.strip() for q in focus.portfolio_search_queries if q and q.strip()]
    if pq:
        lines.append("")
        lines.append("PLANNED PORTFOLIO-WIDE QUERIES:")
        for q in pq:
            lines.append(f"  • {q}")
    return "\n".join(lines)


def news_to_text(news: NewsReview) -> str:
    """Format a NewsReview as compact text for injection into downstream agent prompts."""
    lines = ["=== MARKET CONTEXT (News Agent) ===", ""]
    lines.append(news.macro_context)
    lines.append("")

    if news.market_themes:
        lines.append("Themes: " + " | ".join(news.market_themes))

    if news.key_events:
        lines.append("Key events: " + "; ".join(news.key_events))

    if news.thesis_risks:
        lines.append("Thesis risks: " + "; ".join(news.thesis_risks))

    if news.summary:
        lines.append(news.summary)

    return "\n".join(lines)
