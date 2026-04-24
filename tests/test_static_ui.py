from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_results_modal_contains_actionable_decision_regions() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    assert 'id="portfolio-stance"' in html
    assert 'id="stance-value"' in html
    assert 'id="stance-urgency"' in html
    assert 'id="stance-primary-risk"' in html
    assert 'id="stance-recommended-posture"' in html
    assert 'data-i18n="results.columns.scopePosition"' in html
    assert 'data-i18n="results.columns.decisionLogic"' in html


def test_result_i18n_contains_actionable_decision_labels() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        assert data["results"]["portfolioStance"]
        assert data["results"]["stance"]
        assert data["results"]["urgency"]
        assert data["results"]["primaryRisk"]
        assert data["results"]["recommendedPosture"]
        assert data["results"]["riskAddressed"]
        assert data["results"]["supportingEvidence"]
        assert data["results"]["revisitTrigger"]
        assert data["results"]["columns"]["scopePosition"]
        assert data["results"]["columns"]["decisionLogic"]
        assert data["portfolioStance"]["defensive"]
        assert data["portfolioStance"]["balanced"]
        assert data["portfolioStance"]["opportunistic"]
        assert data["portfolioStance"]["wait"]
        assert data["actionScope"]["portfolio"]
        assert data["actionScope"]["position"]


def test_results_renderer_guards_empty_default_portfolio_stance() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function hasMeaningfulPortfolioStance(stance)" in js
    assert 'normalizePortfolioStance(stance.stance) !== "balanced"' in js
    assert 'normalizePriority(stance.urgency) !== "watch"' in js
    assert "if (hasMeaningfulPortfolioStance(stance))" in js
    assert (
        js.index("if (hasMeaningfulPortfolioStance(stance))")
        < js.index('stanceEl.classList.remove("hidden")')
    )


def test_results_renderer_normalizes_action_scope_aliases() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function normalizeActionScope(action)" in js
    assert '"portfolio-level", "portfolio_level", "book"' in js
    assert '"ticker", "security", "holding"' in js
    assert 'position === "portfolio-level" || position === "portfolio_level"' in js


def test_results_renderer_normalizes_enum_labels_and_classes() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function normalizePriority(value)" in js
    assert '["immediate", "urgent"]' in js
    assert '["this_week", "this-week"]' in js
    assert '["medium", "this-week"]' in js
    assert '["next_review", "next-review"]' in js
    assert 'return PRIORITY_ALIASES.get(normalized) || "watch";' in js
    assert "function normalizeActionType(value)" in js
    assert '["trim", "reduce"]' in js
    assert '["sell", "exit"]' in js
    assert '["buy", "add"]' in js
    assert '["no_action", "no-action"]' in js
    assert 'return ACTION_TYPE_ALIASES.get(normalized) || "monitor";' in js
    assert "function normalizePortfolioStance(value)" in js
    assert '["risk-off", "defensive"]' in js
    assert '["risk_on", "opportunistic"]' in js
    assert '["stand-pat", "wait"]' in js
    assert '["neutral", "balanced"]' in js
    assert 'return PORTFOLIO_STANCE_ALIASES.get(normalized) || "balanced";' in js
    assert "const priority = normalizePriority(a.priority);" in js
    assert "priorityLabel(priority)" in js
    assert "const actionType = normalizeActionType(a.action_type);" in js
    assert "actionTypeLabel(actionType)" in js
    assert "const stanceName = normalizePortfolioStance(stance.stance);" in js
    assert "portfolioStanceLabel(stanceName)" in js


def test_saved_review_paths_accept_raw_manager_payloads() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function isManagerReviewLike(value)" in js
    assert '"executive_summary", "actions", "do_nothing_case"' in js
    assert '"overall_confidence", "portfolio_stance"' in js
    assert "function managerFromReviewBundle(bundle)" in js
    assert "function normalizeReviewBundle(bundle)" in js
    for function_name in [
        "migrateLegacyReviewToHistory",
        "initSavedReview",
        "openSavedReviewFromStorage",
        "renderHistoryList",
    ]:
        start = js.index(f"function {function_name}(")
        end = js.index("\nfunction ", start + 1)
        function_body = js[start:end]
        assert (
            "managerFromReviewBundle(" in function_body
            or "normalizeReviewBundle(" in function_body
        )
        assert "bundle.manager || bundle.planner" not in function_body
