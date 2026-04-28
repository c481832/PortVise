from __future__ import annotations

import csv
import json
import re
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
    assert 'id="actions-list"' in html
    assert 'class="action-card-list"' in html
    assert 'id="overview-top-action"' in html
    assert 'id="computed-evidence"' in html
    assert 'id="factor-risk-chart"' in html
    assert 'id="ticker-risk-chart"' in html
    assert 'id="regime-analog-stats"' in html


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
        assert data["results"]["computedEvidence"]
        assert data["results"]["factorRiskContribution"]
        assert data["results"]["tickerRiskContribution"]
        assert data["results"]["historicalRegimeAnalogs"]
        assert data["results"]["analogWinRate"]
        assert data["results"]["showAnalogDetails"]
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
    assert js.index("if (hasMeaningfulPortfolioStance(stance))") < js.index(
        'stanceEl.classList.remove("hidden")'
    )


def test_results_renderer_normalizes_action_scope_aliases() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function normalizeActionScope(action)" in js
    assert '"portfolio-level", "portfolio_level", "book"' in js
    assert '"ticker", "security", "holding"' in js
    assert 'position === "portfolio-level" || position === "portfolio_level"' in js


def test_results_renderer_builds_scan_friendly_action_cards() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "port/static/style.css").read_text(encoding="utf-8")

    for needle in [
        "function appendActionDecisionDetails(",
        "function renderActionsTable(",
        "function renderActionCards(",
        'document.getElementById("actions-list")',
        "article.className = `action-card action-card--${priority}`;",
        'top.className = "action-card__top";',
        'memo.className = "action-card__memo";',
        'riskColumn.className = "action-card__memo-col";',
        'executionColumn.className = "action-card__memo-col";',
        'setElementText(\n    "overview-top-action",',
        "renderActionsTable(actions);",
        "renderActionCards(actions);",
    ]:
        assert needle in js

    for needle in [
        ".action-card-list",
        ".action-card",
        ".action-card--urgent",
        ".action-card__top",
        ".action-card__rank",
        ".action-card__memo",
        ".action-card__memo-col",
        ".action-memo-block",
        ".actions-table-sr",
    ]:
        assert needle in css


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
            "managerFromReviewBundle(" in function_body or "normalizeReviewBundle(" in function_body
        )
        assert "bundle.manager || bundle.planner" not in function_body


def test_results_modal_contains_share_artifact_regions() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    for needle in [
        'id="share-artifacts"',
        'id="share-privacy-full"',
        'id="share-privacy-masked"',
        'id="share-privacy-anonymous"',
        'id="risk-receipt-preview"',
        'id="receipt-stance"',
        'id="receipt-urgency"',
        'id="receipt-primary-risk"',
        'id="receipt-worst-replay"',
        'id="receipt-top-action"',
        'id="receipt-confidence"',
        'id="copy-risk-receipt"',
        'id="download-risk-receipt"',
        'id="copy-teardown-memo"',
        'id="download-teardown-memo"',
        'data-i18n="share.title"',
        'data-i18n="share.copyReceipt"',
        'data-i18n="share.downloadReceipt"',
        'data-i18n="share.copyMemo"',
        'data-i18n="share.downloadMemo"',
    ]:
        assert needle in html
def test_portfolio_csv_controls_are_wired() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert 'id="portfolio-csv-input"' in html
    assert 'id="import-portfolio-btn"' in html
    assert 'id="save-portfolio-btn"' in html
    assert 'src="/static/app.js?v=36"' in html
    assert 'const SAMPLE_PORTFOLIO_CSV_URL = "/static/sample_portfolio.csv";' in js
    assert "fetch(SAMPLE_PORTFOLIO_CSV_URL)" in js
    assert "function parsePortfolioCsv(text)" in js
    assert 'replace(/^\\uFEFF/, "")' in js
    assert "function readPortfolioCsvFile(file)" in js
    assert "new FileReader()" in js
    assert "function savePortfolioCsv()" in js
    assert "const DEFAULT_POSITIONS" not in js
    assert "async function loadSamplePortfolio(" in js
    assert "loadSamplePortfolio({ silent: true })" in js


def test_sample_portfolio_csv_contains_default_book() -> None:
    csv_path = ROOT / "port/static/sample_portfolio.csv"
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))

    assert rows
    assert csv_path.exists()
    assert rows[0]["portfolio_name"] == "Growth Tilted Core"
    assert rows[0]["benchmark"] == "SPY"
    assert rows[0]["cash_usd"] == "450000"
    assert {row["ticker"] for row in rows} == {"NVDA", "MSFT", "TLT", "XOM", "JPM", "ASML"}
    assert all(row["entry_thesis"] for row in rows)


def test_portfolio_csv_i18n_labels_exist() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        share = data["share"]
        for key in [
            "title",
            "privacy",
            "fullTickers",
            "maskTickers",
            "anonymous",
            "receiptPreview",
            "copyReceipt",
            "downloadReceipt",
            "copyMemo",
            "downloadMemo",
            "receiptKicker",
            "portfolioStance",
            "hiddenRisk",
            "worstReplay",
            "topAction",
            "confidence",
            "generatedBy",
            "notFinancialAdvice",
            "copyReceiptSuccess",
            "copyReceiptError",
            "copyMemoSuccess",
            "copyMemoError",
            "downloadReceiptError",
            "downloadMemoError",
            "noImmediateAction",
            "na",
        ]:
            assert share[key]
        assert data["buttons"]["loadPortfolioCsv"]
        assert data["buttons"]["savePortfolioCsv"]
        assert data["review"]["csvImported"]
        assert data["review"]["csvSaved"]
        assert data["review"]["csvReadError"]
        assert data["review"]["csvMissingTicker"]


def test_llm_config_requires_explicit_save_and_freeform_model_name() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert 'id="cfg-llm-api-key"' in html
    assert 'id="cfg-llm-model" class="cfg-input llm-default-model-input"' in html
    assert 'id="llm-save-config"' in html
    assert 'id="llm-test-config"' in html
    assert 'id="llm-reset-config"' in html
    assert 'id="llm-save-status"' in html
    assert "function saveModelConfig()" in js
    assert "async function testModelConnection()" in js
    assert "function markModelConfigUnsaved()" in js
    assert "localStorage.setItem(LLM_STORAGE_KEY" in js
    assert "j.model_options = savedModelOptionsForStorage(j);" in js
    assert 'document.getElementById("llm-save-config")?.addEventListener("click", saveModelConfig)' in js
    assert 'document.getElementById("llm-test-config")?.addEventListener("click", testModelConnection)' in js
    assert 'document.getElementById("cfg-llm-model")?.addEventListener("input"' in js
    assert "function scheduleSaveModelConfig" not in js
    assert "llm-default-model-select" not in html
    assert "cfg-llm-model-options" not in html
    assert "applySavedModelToAgentSelects(_cfgVal(\"cfg-llm-model\"))" in js
    assert 'sel.innerHTML = ""' not in js


def test_agent_summary_queue_ui_is_wired() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert 'id="agent-summary-popup"' in html
    assert 'id="agent-summary-dismiss"' in html
    assert 'id="agent-summary-count"' in html
    assert 'case "agent_summary":' in js
    assert "function enqueueAgentSummary(msg)" in js
    assert "const agentSummaryQueue = [];" in js
    assert "pendingFinalResult = { output: msg.output, reviewId: currentReviewId };" in js
    assert "void renderResults(finalResult.output, finalResult.reviewId);" in js


def test_agent_summary_i18n_labels_exist() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        assert data["agentSummary"]["agentComplete"]
        assert data["agentSummary"]["queueCount"]
        assert data["agentSummary"]["dismiss"]
        assert data["agentSummary"]["next"]


def test_failure_status_uses_meaningful_reason() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "const STATUS_DETAIL_MAX_CHARS = 64;" in js
    assert "function compactStatusDetail(message" in js
    assert "setGlobalStatus(\"error\", failureDetail);" in js
    assert "setCardState(_currentActiveAgent, \"error\", failureDetail);" in js
    assert 't("status.failedWithReason"' in js
    assert "el.title = detailText;" in js


def test_failure_status_i18n_labels_exist() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        assert data["status"]["failedWithReason"]


def test_computed_evidence_renderer_uses_agent_outputs() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "port/static/style.css").read_text(encoding="utf-8")

    assert "function riskReviewFromAgentOutputs(agentOutputs)" in js
    assert "function regimeReviewFromAgentOutputs(agentOutputs)" in js
    assert "function renderComputedEvidence(agentOutputs = _agentOutputs)" in js
    assert "risk?.factor_risk_contribution" in js
    assert "risk?.marginal_risk_by_ticker" in js
    assert "regime?.historical_outcome" in js
    assert "function firstSentence(text" in js
    assert "function analogContextHtml(message)" in js
    assert "fmtPctAbsFromRatio(hist.win_rate" in js
    assert "fmtPctAbsFromRatio(hist.max_drawdown" in js
    assert "applyResultsFromData(manager, validation, agent_outputs || _agentOutputs);" in js
    assert "applyResultsFromData(mgr, bundle.validation, bundle.agentOutputs || _agentOutputs);" in js
    assert ".evidence-panel--analog" in css
    assert "grid-column: 1 / -1;" in css
    assert ".analog-details summary" in css


def test_share_artifact_helpers_are_present_and_wired() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    for needle in [
        "function deriveShareArtifact(",
        "function renderShareArtifact(",
        "function buildTeardownMemo(",
        "function buildReceiptPlainText(",
        "function buildReceiptSvg(",
        "function applySharePrivacy(",
        "function buildTickerPrivacyMap(",
        "function wireShareControls(",
        "function copyRiskReceipt(",
        "function downloadRiskReceipt(",
        "function copyTeardownMemo(",
        "function downloadTeardownMemo(",
        "currentSharePrivacyMode",
        "currentShareArtifact",
        "wireShareControls();",
        "renderShareArtifact();",
    ]:
        assert needle in js


def test_share_privacy_masking_is_case_insensitive_and_token_bound() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert (
        'new RegExp(`(^|[^A-Za-z0-9.-])(${escapeRegExp(symbol)})(?=$|[^A-Za-z0-9.-])`, "gi")' in js
    )


def test_teardown_memo_reads_theme_synthesis_dominant_themes() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "theme?.synthesis?.dominant_themes" in js
    assert "theme?.dominant_themes" in js
    assert js.index("theme?.synthesis?.dominant_themes") < js.index("theme?.dominant_themes")


def test_receipt_svg_wraps_long_lines() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function wrapReceiptSvgLine(line, maxChars = 82, maxRows = 2)" in js
    assert "split(/\\s+/)" in js
    assert '"+ "...";' in js or "`${last}...`" in js


def test_review_start_blocks_missing_quote_prices() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function positionRowsMissingReadyQuotes()" in js
    assert 'showToast(t("review.marketDataRequired"' in js
    assert "const missingQuotes = positionRowsMissingReadyQuotes();" in js
    assert js.index("const missingQuotes = positionRowsMissingReadyQuotes();") < js.index(
        "const portfolio = buildPortfolio();"
    )

    en = json.loads((ROOT / "port/static/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "port/static/locales/zh-CN.json").read_text(encoding="utf-8"))
    assert en["review"]["marketDataRequired"]
    assert zh["review"]["marketDataRequired"]


def test_error_event_marks_running_agent_cards_error() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "function markRunningCardsErrored()" in js
    error_case = js[js.index('case "error":') : js.index('case "stopped":')]
    assert "markRunningCardsErrored();" in error_case

    build_svg_start = js.index("function buildReceiptSvg(")
    build_svg_end = js.index("\nfunction markdownList", build_svg_start)
    build_svg_body = js[build_svg_start:build_svg_end]
    assert "wrapReceiptSvgLine(line)" in build_svg_body
    assert "rows.length >= 13" in build_svg_body
    assert 'height="420"' in build_svg_body


def test_saved_review_bundle_carries_portfolio_for_share_privacy() -> None:
    js = (ROOT / "port/static/app.js").read_text(encoding="utf-8")

    assert "portfolio: buildPortfolio()," in js
    assert "currentResultsView = { manager, validation, bundle" in js

    def function_body(name: str) -> str:
        start = js.index(f"function {name}(")
        end = js.find("\nfunction ", start + 1)
        return js[start:] if end == -1 else js[start:end]

    def calls_apply_results_with_bundle(body: str) -> bool:
        return bool(re.search(r"applyResultsFromData\([^)]*\bbundle\b[^)]*\)", body, re.S))

    for function_name in [
        "openSavedReviewFromStorage",
        "renderHistoryList",
        "renderResults",
    ]:
        assert calls_apply_results_with_bundle(function_body(function_name))
