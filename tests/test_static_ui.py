from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_results_modal_contains_actionable_decision_regions() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    assert 'id="portfolio-stance"' in html
    assert 'class="portfolio-stance decision-summary hidden"' in html
    assert 'id="exec-summary"' in html
    assert 'data-i18n="results.verdict"' in html
    assert 'id="verdict-action-timing"' in html
    assert 'id="verdict-horizon"' in html
    assert 'id="stance-primary-risk"' in html
    assert 'id="stance-recommended-posture"' in html
    assert 'data-i18n="results.columns.scopePosition"' in html
    assert 'data-i18n="results.columns.decisionLogic"' in html
    assert 'id="actions-list"' in html
    assert 'class="action-card-list"' in html
    assert 'id="overview-top-action"' in html
    assert 'id="do-nothing"' in html
    assert 'id="summary-risk-attribution"' not in html
    assert 'id="summary-factor-risk-attribution"' not in html
    assert 'id="summary-ticker-risk-attribution"' not in html
    assert 'id="agent-output-section"' not in html
    assert 'id="agent-output-list"' not in html
    assert 'data-i18n="agentOutput.title"' not in html
    assert 'id="computed-evidence"' not in html
    assert 'id="factor-risk-chart"' not in html
    assert 'id="ticker-risk-chart"' not in html
    assert 'id="regime-analog-stats"' not in html
    assert html.index('id="portfolio-stance"') < html.index('data-i18n="results.doNothingCase"')
    assert html.index('data-i18n="results.doNothingCase"') < html.index(
        'data-i18n="results.actionPlan"'
    )


def test_result_i18n_contains_actionable_decision_labels() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        assert data["results"]["decision"]
        assert data["results"]["verdict"]
        assert data["results"]["actionTiming"]
        assert data["results"]["investmentHorizon"]
        assert data["results"]["primaryRisk"]
        assert data["results"]["recommendedPosture"]
        assert data["results"]["factorRiskContribution"]
        assert data["results"]["riskAddressed"]
        assert data["results"]["supportingEvidence"]
        assert data["results"]["revisitTrigger"]
        assert data["agentOutput"]["title"]
        assert data["agentOutput"]["note"]
        assert data["agentOutput"]["toggle"]
        assert data["results"]["columns"]["scopePosition"]
        assert data["results"]["columns"]["decisionLogic"]
        assert data["actionScope"]["portfolio"]
        assert data["actionScope"]["position"]


def test_results_modal_contains_agent_analysis_tabs() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    assert 'id="open-agent-analysis"' in html
    assert 'id="agent-analysis-modal"' in html
    assert 'id="agent-analysis-modal-close"' in html
    assert 'id="agent-analysis"' in html
    assert 'id="agent-analysis-panels"' in html
    for agent in ["planner", "news", "risk", "regime", "theme"]:
        assert f'id="agent-tab-{agent}"' in html
        assert f'id="agent-panel-{agent}"' in html
    assert 'id="agent-tab-feedback"' in html
    assert 'id="agent-panel-feedback"' in html
    assert 'id="agent-tab-manager"' not in html
    assert 'id="agent-panel-manager"' not in html
    assert "data-refinement-form" not in html


def test_run_review_can_include_matching_past_feedback() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert 'id="past-feedback-modal"' in html
    assert 'id="past-feedback-list"' in html
    assert 'id="past-feedback-skip"' in html
    assert 'id="past-feedback-include"' in html
    assert "async function fetchPastFeedbackMatch(portfolio)" in js
    assert 'fetch("/api/reviews/feedback-candidates", {' in js
    assert "function showPastFeedbackModal(startBody, match)" in js
    assert "function runPendingReviewWithFeedback()" in js
    assert "startBody.inherited_feedback = inheritedFeedback;" in js
    assert '${index < 3 ? "checked" : ""}' in js


def test_sidebar_shows_data_loader_as_data_agent() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    assert 'id="data-loader-panel"' not in html
    assert 'id="card-data"' in html
    assert 'data-agent="data"' in html
    assert 'data-i18n="dataLoader.title">Data</span>' in html
    assert html.count('data-i18n="dataLoader.title">Data</span>') == 1
    assert html.index('id="card-data"') < html.index('id="card-planner"')


def test_sidebar_uses_per_agent_run_time() -> None:
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/main.css").read_text(encoding="utf-8")
    locale = (ROOT / "frontend/public/locales/en.json").read_text(encoding="utf-8")

    assert 'class="sidebar-run-time"' not in html
    assert "Time used to run" not in html
    assert 'id="review-elapsed-value"' not in html
    assert "function renderAgentElapsed(agent)" in js
    assert "fmtAgentRunTime(agentElapsedSeconds(agent))" in js
    assert "renderAgentElapsed(agent);" in js
    assert ".agent-elapsed" in css
    assert '"runTime": "Run time {duration}"' in locale


def test_agent_analysis_i18n_contains_refinement_labels() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        aa = data["agentAnalysis"]
        assert aa["title"]
        assert aa["modalTitle"]
        assert aa["open"]
        assert aa["delete"]
        assert aa["feedback"]["tab"]
        assert aa["feedback"]["submit"]
        assert aa["feedback"]["saved"]
        assert aa["feedback"]["failed"]
        assert aa["risk"]["userScenarios"]
        assert aa["risk"]["addScenario"]
        assert aa["regime"]["userPeriods"]
        assert aa["regime"]["addPeriod"]
        assert aa["theme"]["userThemes"]
        assert aa["theme"]["addTheme"]


def test_agent_analysis_modal_has_single_visible_title() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    assert (
        'id="agent-analysis-modal-title" data-i18n="agentAnalysis.modalTitle">'
        "Agent analysis</h2>"
    ) in html
    assert 'data-i18n="agentAnalysis.kicker">Agent analysis</p>' not in html
    assert 'data-i18n="agentAnalysis.title">Agent analysis</h3>' not in html
    assert (
        'id="agent-analysis" class="agent-analysis" '
        'aria-labelledby="agent-analysis-modal-title"'
    ) in html


def test_news_agent_analysis_has_no_user_input_panel() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    news_renderer = js[
        js.index("function renderNewsAnalysisTab(view)"):
        js.index("function renderRiskAnalysisTab(view)")
    ]
    assert 'refinementPanelHtml("news"' not in news_renderer
    assert 'data-refinement-form="news"' not in js


def test_news_considered_uses_planner_topics_as_frame() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    locale = json.loads((ROOT / "frontend/public/locales/en.json").read_text(encoding="utf-8"))

    assert "function plannedNewsResearchSections(view, runs)" in js
    assert "function newsFocusFromView(view)" in js
    assert "focus.portfolio_search_queries" in js
    assert "focus.position_goals" in js
    assert 't("agentAnalysis.news.plannerTopics")' not in js
    assert 't("agentAnalysis.news.tickerSearches")' in js
    assert "newsResearchSectionsHtml(view, queries)" in js
    assert "plannerTopics" not in locale["agentAnalysis"]["news"]
    assert locale["agentAnalysis"]["news"]["tickerSearches"]


def test_agent_analysis_includes_planner_output_tab() -> None:
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert 'id="agent-tab-planner"' in html
    assert 'id="agent-panel-planner"' in html
    assert 'let activeAgentAnalysisTab = "planner";' in js
    assert "function renderPlannerAnalysisTab(view)" in js
    assert "view?.agentOutputs?.planner?.news_focus" in js
    assert 't("agentAnalysis.planner.portfolioGoal")' in js
    assert 't("agentAnalysis.planner.macroTopics")' in js
    assert "listHtml(focus.portfolio_search_queries)" in js
    assert "planner: renderPlannerAnalysisTab" in js
    assert '"planner", "news", "risk", "regime", "theme"' in js
    assert "renderManagerAnalysisTab" not in js


def test_agent_analysis_js_persists_review_refinements() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    for needle in [
        'let activeAgentAnalysisTab = "planner";',
        "function renderAgentAnalysisTabs(view = currentResultsView)",
        "function showAgentAnalysisModal()",
        "function hideAgentAnalysisModal(",
        'document.getElementById("open-agent-analysis")?.addEventListener('
        '"click", showAgentAnalysisModal);',
        "function renderPlannerAnalysisTab(view)",
        "function renderNewsAnalysisTab(view)",
        "function renderRiskAnalysisTab(view)",
        "function renderRegimeAnalysisTab(view)",
        "function renderThemeAnalysisTab(view)",
        "function renderFeedbackAnalysisTab(view)",
        "function feedbackLatestSnapshotHtml(view, rounds)",
        "function feedbackActionPreviewHtml(manager",
        "async function submitUserFeedback(comment)",
        "wireAgentAnalysisControls();",
        "renderAgentAnalysisTabs(currentResultsView);",
        "feedbackRounds: Array.isArray(data.feedback_rounds)",
        'fetch(`/api/review/${encodeURIComponent(reviewId)}/feedback`, {',
    ]:
        assert needle in js


def test_agent_analysis_helpers_are_available_before_tab_renderers() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    for helper, renderer in [
        (
            "function riskReviewFromAgentOutputs(agentOutputs)",
            "function renderRiskAnalysisTab(view)",
        ),
        (
            "function regimeReviewFromAgentOutputs(agentOutputs)",
            "function renderRegimeAnalysisTab(view)",
        ),
        ("function sortedMetricEntries(values", "function metricBarsHtml(values"),
    ]:
        assert js.index(helper) < js.index(renderer)


def test_results_renderer_guards_empty_default_portfolio_verdict() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function hasMeaningfulPortfolioVerdict(verdict)" in js
    assert '"investment_horizon"' in js
    assert '"horizon_detail"' in js
    assert 'normalizePriority(verdict.action_timing) !== "watch"' in js
    assert "const hasDecisionSummary =" in js
    assert "hasMeaningfulPortfolioVerdict(verdict) ||" in js
    assert "if (hasDecisionSummary)" in js
    assert js.index("if (hasDecisionSummary)") < js.index('stanceEl.classList.remove("hidden")')


def test_results_renderer_normalizes_action_scope_aliases() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function normalizeActionScope(action)" in js
    assert '"portfolio-level", "portfolio_level", "book"' in js
    assert '"ticker", "security", "holding"' in js
    assert 'position === "portfolio-level" || position === "portfolio_level"' in js


def test_results_renderer_builds_scan_friendly_action_cards() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/main.css").read_text(encoding="utf-8")

    for needle in [
        "function appendActionDecisionDetails(",
        "function renderActionsTable(",
        "function renderActionCards(",
        'document.getElementById("actions-list")',
        "article.className = `action-card action-card--${priority}`;",
        'top.className = "action-card__top";',
        'top.setAttribute("aria-expanded", "false");',
        "memo.hidden = true;",
        'top.addEventListener("click", () => {',
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
        ".action-card__toggle",
        ".action-card__memo",
        ".action-card__memo[hidden]",
        ".action-card__memo-col",
        ".action-memo-block",
        ".actions-table-sr",
    ]:
        assert needle in css


def test_results_renderer_normalizes_enum_labels_and_classes() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

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
    assert "const priority = normalizePriority(a.priority);" in js
    assert "priorityLabel(priority)" in js
    assert "const actionType = normalizeActionType(a.action_type);" in js
    assert "actionTypeLabel(actionType)" in js
    assert 'document.getElementById("verdict-action-timing")' in js
    assert 'document.getElementById("verdict-horizon")' in js
    assert "verdictData.investment_horizon" in js
    assert "verdictData.horizon_detail" in js


def test_saved_review_paths_accept_raw_manager_payloads() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function isManagerReviewLike(value)" in js
    assert '"executive_summary", "actions", "do_nothing_case"' in js
    assert '"portfolio_verdict"' in js
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


def test_results_modal_omits_risk_receipt_regions() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")

    for needle in [
        'id="share-artifacts"',
        'id="share-privacy-full"',
        'id="share-privacy-masked"',
        'id="share-privacy-anonymous"',
        'id="risk-receipt-preview"',
        'id="receipt-action-timing"',
        'id="receipt-investment-horizon"',
        'id="receipt-primary-risk"',
        'id="receipt-worst-replay"',
        'id="receipt-top-action"',
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
        assert needle not in html


def test_portfolio_csv_controls_are_wired() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert 'id="portfolio-csv-input"' in html
    assert 'id="import-portfolio-btn"' in html
    assert 'id="save-portfolio-btn"' in html
    assert re.search(r'src="/static/app-[^"]+\.js"', html)
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
            "actionTiming",
            "investmentHorizon",
            "hiddenRisk",
            "worstReplay",
            "topAction",
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
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert 'id="cfg-llm-api-key"' in html
    assert 'id="cfg-llm-base-url"' in html
    assert 'id="cfg-llm-model"' in html
    assert 'id="cfg-model-extra-args"' in html
    assert 'id="cfg-add-model-input"' in html
    assert 'id="cfg-add-model-btn"' in html
    assert 'id="llm-model-library"' in html
    assert 'id="llm-per-agent-details"' in html
    assert 'id="llm-save-config"' in html
    assert 'id="llm-test-config"' in html
    assert 'id="llm-reset-config"' in html
    assert 'id="llm-save-status"' in html
    assert "function saveModelConfig()" in js
    assert "async function testModelConnection()" in js
    assert "function markModelConfigUnsaved()" in js
    assert "function addModelToLibrary(name)" in js
    assert "function removeModelFromLibrary(name)" in js
    assert "function renderModelLibrary()" in js
    assert "model_extra_args" in js
    assert "collectAgentReasoningOverrides()" not in js
    assert "agent-reasoning-checkbox" not in js
    assert "LLM_STORAGE_KEY" not in js
    assert "_modelConfigResetPending" not in js
    assert "delete persisted.llm_api_key;" not in js
    assert "ignoreSaved" not in js
    assert 'await fetch("/api/config", {' in js
    assert 'method: "POST"' in js
    assert 'await fetch("/api/config", { method: "DELETE" })' in js
    assert "if (apiKey) payload.llm_api_key = apiKey;" in js
    assert 'async function loadModelConfigUi(statusKey = "loaded")' in js
    assert "renderAgentModelSelects(server.default_agent_models);" in js
    assert "mergeModelOptions(server.model_options, server.llm_model)" in js
    assert (
        'document.getElementById("llm-save-config")?.addEventListener("click", saveModelConfig)'
        in js
    )
    assert (
        'document.getElementById("llm-test-config")?.addEventListener("click", testModelConnection)'
        in js
    )
    assert (
        'document.getElementById("llm-reset-config")?.addEventListener("click", resetModelConfig)'
        in js
    )
    assert "fast_llm_base_url" not in js
    assert "fast_llm_model" not in js
    assert "cfg-endpoint-badge--fast" not in html
    assert "cfg-endpoint-badge--primary" not in html
    assert "function scheduleSaveModelConfig" not in js


def test_agent_summary_queue_ui_is_wired() -> None:
    html = (ROOT / "port/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert 'id="agent-summary-popup"' in html
    assert 'id="agent-summary-dismiss"' in html
    assert 'id="agent-summary-count"' in html
    assert 'case "agent_summary":' in js
    assert "function enqueueAgentSummary(msg)" in js
    assert "const agentSummaryQueue = [];" in js
    assert "pendingFinalResult = { output: msg.output, reviewId: currentReviewId };" in js
    assert "void renderFinalResultOnce(pendingFinalResult);" in js
    assert "void renderFinalResultOnce(finalResult);" in js


def test_final_review_renders_from_done_snapshot_fallback() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "eventSource.onerror = async () =>" in js
    assert "const snapshot = reviewId ? await syncReviewSnapshot(reviewId) : null;" in js
    assert (
        'snapshot?.status === "done" || snapshot?.status === "stopped" || '
        'snapshot?.status === "error"'
    ) in js
    assert 'if (data.status === "done")' in js
    assert 'else if (data.status === "error")' in js
    assert "data.last_error" in js
    assert "await renderFinalResultOnce({" in js
    assert "output: data.agent_outputs?.manager" in js
    assert "final_state?.manager_review" in js
    assert "agent_outputs?.manager?.manager_review" in js
    assert "attempt < 3" in js
    assert "void renderFinalResultOnce(finalResult, attempt + 1);" in js


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
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "const STATUS_DETAIL_MAX_CHARS = 64;" in js
    assert "function compactStatusDetail(message" in js
    assert 'setGlobalStatus("error", failureDetail);' in js
    assert "const failedAgent = msg.agent || _currentActiveAgent;" in js
    assert 'setCardState(failedAgent, "error", failureDetail);' in js
    assert 't("status.failedWithReason"' in js
    assert "el.title = detailText;" in js


def test_failure_status_i18n_labels_exist() -> None:
    for locale_path in [
        ROOT / "port/static/locales/en.json",
        ROOT / "port/static/locales/zh-CN.json",
    ]:
        data = json.loads(locale_path.read_text(encoding="utf-8"))
        assert data["status"]["failedWithReason"]


def test_agent_outputs_are_not_rendered_in_decision_report() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/main.css").read_text(encoding="utf-8")

    assert "function renderAgentOutputList(agentOutputs = _agentOutputs)" not in js
    assert 'document.getElementById("agent-output-section")' not in js
    assert "renderAgentOutputList(agentOutputs);" not in js
    assert "applyResultsFromData(manager, validation, agent_outputs || _agentOutputs);" in js
    assert (
        "applyResultsFromData(mgr, bundle.validation, bundle.agentOutputs || _agentOutputs);" in js
    )
    assert ".agent-output-section" not in css
    assert ".agent-output-item summary" not in css
    assert ".agent-output-item pre" not in css


def test_risk_attribution_is_not_rendered_in_decision_summary() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/main.css").read_text(encoding="utf-8")

    assert "function renderSummaryRiskAttribution(agentOutputs)" not in js
    assert "renderSummaryRiskMetricList" not in js
    assert "renderSummaryRiskAttribution(agentOutputs);" not in js
    assert ".summary-risk-attribution" not in css
    assert ".summary-risk-metric" not in css


def test_share_artifact_helpers_are_not_wired_into_report() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

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
    ]:
        assert needle in js
    assert "wireShareControls();" not in js


def test_share_privacy_masking_is_case_insensitive_and_token_bound() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert (
        'new RegExp(`(^|[^A-Za-z0-9.-])(${escapeRegExp(symbol)})(?=$|[^A-Za-z0-9.-])`, "gi")' in js
    )


def test_teardown_memo_reads_theme_synthesis_dominant_themes() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "theme?.synthesis?.dominant_themes" in js
    assert "theme?.dominant_themes" in js
    assert js.index("theme?.synthesis?.dominant_themes") < js.index("theme?.dominant_themes")


def test_receipt_svg_wraps_long_lines() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function wrapReceiptSvgLine(line, maxChars = 82, maxRows = 2)" in js
    assert "split(/\\s+/)" in js
    assert '"+ "...";' in js or "`${last}...`" in js


def test_review_start_auto_refreshes_missing_quote_prices() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function ensureReviewDate()" in js
    assert 'params.set("actions_start", ensureReviewDate());' in js
    assert "meta.review_date || todayLocalIso()" in js
    assert "function positionRowsMissingReadyQuotes()" in js
    assert "async function refreshMissingQuotesForReview()" in js
    assert "missingQuotes = await refreshMissingQuotesForReview();" in js
    assert 'showToast(t("review.marketDataRequired"' in js
    assert js.index("missingQuotes = await refreshMissingQuotesForReview();") < js.index(
        'showToast(t("review.marketDataRequired"'
    )

    en = json.loads((ROOT / "port/static/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((ROOT / "port/static/locales/zh-CN.json").read_text(encoding="utf-8"))
    assert en["review"]["marketDataRequired"]
    assert en["review"]["marketDataRefreshing"]
    assert zh["review"]["marketDataRequired"]
    assert zh["review"]["marketDataRefreshing"]


def test_error_event_marks_running_agent_cards_error() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

    assert "function markRunningCardsErrored()" in js
    error_case = js[js.index('case "error":') : js.index('case "stopped":')]
    assert "markRunningCardsErrored();" in error_case
    assert "const failedAgent = msg.agent || _currentActiveAgent;" in error_case
    assert 'setCardState(failedAgent, "error", failureDetail);' in error_case

    build_svg_start = js.index("function buildReceiptSvg(")
    build_svg_end = js.index("\nfunction markdownList", build_svg_start)
    build_svg_body = js[build_svg_start:build_svg_end]
    assert "wrapReceiptSvgLine(line)" in build_svg_body
    assert "rows.length >= 13" in build_svg_body
    assert 'height="420"' in build_svg_body


def test_sidebar_agent_cards_render_status_only() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/main.css").read_text(encoding="utf-8")

    toggle_start = js.index("function toggleAgentStepStatus(")
    toggle_end = js.index("\nfunction recordStep", toggle_start)
    toggle_body = js[toggle_start:toggle_end]

    assert "function renderCardOutput(" not in js
    assert "renderCardOutput(" not in js
    assert "agentOutputHtml(agent, _agentOutputs[agent])" in js
    assert 'class="card-body' not in html
    assert ".card-body" not in css
    assert "agent-stream-row" in html
    assert 'body.classList.toggle("hidden", !opening);' not in toggle_body


def test_saved_review_bundle_carries_portfolio_for_share_privacy() -> None:
    js = (ROOT / "frontend/src/app.js").read_text(encoding="utf-8")

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
