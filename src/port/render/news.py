"""Render news focus and news review as prompt text."""

from __future__ import annotations

from port.models.news import NewsFocus, NewsReview


def news_focus_to_text(focus: NewsFocus) -> str:
    """What the news agent should prioritise: portfolio goal + each position thesis."""
    lines = [
        "=== SEARCH PRIORITIES (use these to filter what matters) ===",
        "",
        "1) PORTFOLIO GOAL — prioritise macro and market developments that affect this objective:",
        focus.portfolio_goal or "(none stated)",
        "",
        "2) POSITION GOALS (entry thesis per name) — prioritise ticker/sector news and flows "
        "that support or challenge each thesis:",
    ]
    for pg in focus.position_goals:
        g = pg.goal.strip() if pg.goal else ""
        lines.append(f"  • {pg.ticker}: {g or '(no thesis stated)'}")
        lq = (pg.latest_news_query or "").strip()
        if lq:
            lines.append(f"      → planned query (latest news): {lq}")
    pq = [q.strip() for q in focus.portfolio_search_queries if q and q.strip()]
    if pq:
        lines.append("")
        lines.append("3) PLANNED SEARCH QUERIES (portfolio-wide — run with search tools first):")
        for q in pq:
            lines.append(f"  • {q}")
    lines.append("")
    lines.append(
        "Tailor key_events, market_themes, thesis_risks, and macro_context toward items above "
        "where recent facts exist; deprioritise generic filler unrelated to these goals."
    )
    return "\n".join(lines)

def news_to_text(news: NewsReview) -> str:
    """Render a NewsReview as compact text for injection into downstream agent prompts."""
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
