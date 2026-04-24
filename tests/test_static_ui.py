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
    assert '["urgent", "this-week", "next-review", "watch"]' in js
    assert 'return PRIORITY_VALUES.has(normalized) ? normalized : "watch";' in js
    assert "function normalizeActionType(value)" in js
    assert '["reduce", "exit", "hedge", "rotate", "add", "monitor", "no-action"]' in js
    assert 'return ACTION_TYPE_VALUES.has(normalized) ? normalized : "monitor";' in js
    assert "function normalizePortfolioStance(value)" in js
    assert '["defensive", "balanced", "opportunistic", "wait"]' in js
    assert 'return PORTFOLIO_STANCE_VALUES.has(normalized) ? normalized : "balanced";' in js
    assert "const priority = normalizePriority(a.priority);" in js
    assert "priorityLabel(priority)" in js
    assert "const actionType = normalizeActionType(a.action_type);" in js
    assert "actionTypeLabel(actionType)" in js
    assert "const stanceName = normalizePortfolioStance(stance.stance);" in js
    assert "portfolioStanceLabel(stanceName)" in js
