import {
  applyTranslations,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatPrice,
  getLocale,
  getLocaleLabel,
  initI18n,
  onLocaleChange,
  setLocale,
  t,
} from "./i18n.js";

// ── CSV portfolio import/export ────────────────────────────────────────────
const SAMPLE_PORTFOLIO_CSV_URL = "/static/sample_portfolio.csv";
const PORTFOLIO_CSV_COLUMNS = [
  "portfolio_name",
  "benchmark",
  "cash_usd",
  "review_date",
  "context_note",
  "ticker",
  "name",
  "sector",
  "asset_class",
  "quantity",
  "entry_thesis",
];
const POSITION_ASSET_CLASSES = ["equity", "bond", "commodity", "fx", "crypto"];

let currentReviewId = null;
let eventSource = null;
let lastStartBody = null;
let currentGlobalStatusState = "idle";
let currentDataLoaderUi = {
  state: "idle",
  detailKey: "dataLoader.waitingHistoryStatus",
  detailVars: {},
  detailText: "",
  allowRetry: false,
};
let currentResultsView = null;
let activeAgentAnalysisTab = "news";
let currentSharePrivacyMode = "masked";
let currentShareArtifact = null;
let currentAgentOutputUpdatedAt = {};
const agentStepHistory = {};

const MAX_STEP_HISTORY = 60;
const MAX_PERSISTED_STRING_CHARS = 3000;
const MAX_PERSISTED_STEP_LOGS = 25;
let drawerRawMode = false;

// ── Agent progress state ──────────────────────────────────────────────────
const agentStartTimes = {};
const agentEndTimes = {};
const agentTimerIds = {};
const agentStepProgress = {}; // agent -> { active: N, done: Set<N> }
const AGENT_CARD_NAMES = new Set(["planner","news","risk","regime","theme","validation","manager"]);

const AGENT_SVG = {
  planner:    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01"/></svg>',
  data:       '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>',
  news:       '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/></svg>',
  risk:       '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4M12 16h.01"/></svg>',
  regime:     '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20M2 12h20"/></svg>',
  theme:      '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
  validation: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/><path d="M8.5 2h7M7 16.5h10"/></svg>',
  manager:    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/></svg>',
};

const AGENT_PLANS = {
  planner:    { labelKey:"agents.planner.label", descKey:"agents.planner.desc", stepKeys:["agents.planner.steps.0", "agents.planner.steps.1"] },
  data:       { labelKey:"agents.data.label", descKey:"agents.data.desc", stepKeys:["agents.data.steps.0"] },
  news:       { labelKey:"agents.news.label", descKey:"agents.news.desc", stepKeys:["agents.news.steps.0", "agents.news.steps.1"] },
  risk:       { labelKey:"agents.risk.label", descKey:"agents.risk.desc", stepKeys:["agents.risk.steps.0"] },
  regime:     { labelKey:"agents.regime.label", descKey:"agents.regime.desc", stepKeys:["agents.regime.steps.0"] },
  theme:      { labelKey:"agents.theme.label", descKey:"agents.theme.desc", stepKeys:["agents.theme.steps.0"] },
  validation: { labelKey:"agents.validation.label", descKey:"agents.validation.desc", stepKeys:["agents.validation.steps.0"] },
  manager:    { labelKey:"agents.manager.label", descKey:"agents.manager.desc", stepKeys:["agents.manager.steps.0"] },
};

// ── Plan modal state ──────────────────────────────────────────────────────
let _drawerOpen = false;
let _drawerAgent = null;
let _drawerPinned = false;
let _autoFollowTimer = null;
const AUTO_FOLLOW_DELAY_MS = 3000;
const _agentOutputs = {};
const agentSummaryQueue = [];
let activeAgentSummary = null;
let pendingFinalResult = null;
let finalResultReviewId = null;
let finalResultRenderInFlightId = null;
const quoteTimers = new WeakMap();
const LAST_REVIEW_STORAGE_KEY = "portAdvisorLastReview";
const REVIEW_HISTORY_STORAGE_KEY = "portAdvisorReviewHistory";
const MAX_REVIEW_HISTORY = 30;
const SIDEBAR_WIDTH_STORAGE_KEY = "portAdvisorSidebarWidth";
const SIDEBAR_MIN_PX = 180;
const SIDEBAR_MAX_PX = 560;
const LLM_STORAGE_KEY = "portAdvisorModelConfig";
let _currentModelConfigBaseModel = "";
const DATA_LOADER_ERROR_RE = /(missing portfolio history for analog matching|missing price history for holdings|yfinance returned no data for analog matching|insufficient historical windows for analog matching)/i;
const DATA_LOADER_HISTORY_MAX = 12;
const STATUS_DETAIL_MAX_CHARS = 64;
const dataLoaderHistory = [];
const PRIORITY_ALIASES = new Map([
  ["urgent", "urgent"],
  ["immediate", "urgent"],
  ["critical", "urgent"],
  ["high", "urgent"],
  ["this-week", "this-week"],
  ["this_week", "this-week"],
  ["thisweek", "this-week"],
  ["medium", "this-week"],
  ["short-term", "this-week"],
  ["next-review", "next-review"],
  ["next_review", "next-review"],
  ["low", "next-review"],
  ["medium-term", "next-review"],
  ["watch", "watch"],
]);
const ACTION_TYPE_ALIASES = new Map([
  ["reduce", "reduce"],
  ["trim", "reduce"],
  ["exit", "exit"],
  ["sell", "exit"],
  ["hedge", "hedge"],
  ["rotate", "rotate"],
  ["add", "add"],
  ["buy", "add"],
  ["monitor", "monitor"],
  ["hold", "monitor"],
  ["no-action", "no-action"],
  ["no_action", "no-action"],
]);
const PORTFOLIO_STANCE_ALIASES = new Map([
  ["defensive", "defensive"],
  ["risk-off", "defensive"],
  ["risk_off", "defensive"],
  ["de-risk", "defensive"],
  ["derisk", "defensive"],
  ["opportunistic", "opportunistic"],
  ["risk-on", "opportunistic"],
  ["risk_on", "opportunistic"],
  ["offensive", "opportunistic"],
  ["wait", "wait"],
  ["hold", "wait"],
  ["stand-pat", "wait"],
  ["stand_pat", "wait"],
  ["no-action", "wait"],
  ["no_action", "wait"],
  ["balanced", "balanced"],
  ["neutral", "balanced"],
]);
const MANAGER_REVIEW_FIELDS = [
  "executive_summary", "actions", "do_nothing_case",
  "overall_confidence", "portfolio_stance",
];

/** LLM-using pipeline slots (data is tools-only / no LLM). */
const AGENT_MODEL_SLOTS = [
  { id: "planner", labelKey: "agents.planner.label", hintKey: "llm.agentHints.fastSearchContext" },
  { id: "news_tools", labelKey: "agents.news.label", hintKey: "llm.agentHints.fastEndpoint" },
  { id: "news_synthesis", labelKey: "agents.news.label" },
  { id: "risk", labelKey: "agents.risk.label" },
  { id: "regime", labelKey: "agents.regime.label" },
  { id: "theme", labelKey: "agents.theme.label" },
  { id: "validation", labelKey: "agents.validation.label" },
  { id: "manager", labelKey: "agents.manager.label" },
];

function getAgentPlan(agent) {
  const plan = AGENT_PLANS[agent];
  if (!plan) return { label: agent, desc: "", steps: [] };
  return {
    label: t(plan.labelKey),
    desc: t(plan.descKey),
    steps: plan.stepKeys.map((key) => t(key)),
  };
}

function _cfgVal(id) {
  const el = document.getElementById(id);
  return el?.value?.trim() || "";
}

function _ensureOption(select, value) {
  if (!value || !select) return;
  const exists = Array.from(select.options).some((o) => o.value === value);
  if (!exists) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = value;
    select.appendChild(o);
  }
}

function renderModelNameInput(inputEl, modelOptions, serverDefaultName, savedOverride) {
  if (!inputEl) return;
  const opts = Array.isArray(modelOptions) ? modelOptions : [];
  const fallback = opts[0] || (serverDefaultName && String(serverDefaultName).trim()) || "";
  inputEl.value = (savedOverride && String(savedOverride).trim()) || fallback;
}

function mergeModelOptions(...groups) {
  const out = [];
  const seen = new Set();
  for (const group of groups) {
    const values = Array.isArray(group) ? group : [group];
    for (const value of values) {
      const text = value && String(value).trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      out.push(text);
    }
  }
  return out;
}

function renderAgentModelSelects(modelOptions, defaultAgentModels, savedAgentModels, selectedModel) {
  const wrap = document.getElementById("llm-agent-model-rows");
  if (!wrap) return;
  wrap.innerHTML = "";
  const saved = savedAgentModels && typeof savedAgentModels === "object" ? savedAgentModels : {};
  for (const slot of AGENT_MODEL_SLOTS) {
    const row = document.createElement("div");
    row.className = "cfg-field cfg-field--agent";

    const lab = document.createElement("label");
    lab.setAttribute("for", `cfg-agent-${slot.id}`);
    lab.appendChild(document.createTextNode(t(slot.labelKey)));
    if (slot.hintKey) {
      const sp = document.createElement("span");
      sp.className = "cfg-agent-hint";
      sp.textContent = ` (${t(slot.hintKey)})`;
      lab.appendChild(sp);
    }

    const sel = document.createElement("select");
    sel.className = "cfg-select agent-model-select";
    sel.id = `cfg-agent-${slot.id}`;
    sel.dataset.agentKey = slot.id;

    const model =
      (saved[slot.id] && String(saved[slot.id]).trim()) ||
      (selectedModel && String(selectedModel).trim()) ||
      (defaultAgentModels[slot.id] && String(defaultAgentModels[slot.id]).trim()) ||
      "";
    const values = mergeModelOptions(modelOptions, model);
    for (const m of values) {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      sel.appendChild(o);
    }

    if (model) sel.value = model;

    row.appendChild(lab);
    row.appendChild(sel);
    wrap.appendChild(row);
    sel.addEventListener("change", markModelConfigUnsaved);
  }
}

function syncAgentModelSelects(modelName) {
  const model = modelName && String(modelName).trim();
  if (!model) return;
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    _ensureOption(sel, model);
    sel.value = model;
  });
}

function applySavedModelToAgentSelects(modelName) {
  const model = modelName && String(modelName).trim();
  if (!model) return;
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    const current = sel.value?.trim() || "";
    _ensureOption(sel, model);
    if (!current || current === _currentModelConfigBaseModel) {
      sel.value = model;
    }
  });
}

function savedModelOptionsForStorage(basePayload) {
  let existing = {};
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY);
    if (raw) existing = JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return mergeModelOptions(
    existing.model_options,
    basePayload?.model_options,
    basePayload?.llm_model,
    Array.from(document.querySelectorAll("select.agent-model-select")).map((sel) => sel.value),
  );
}

function setModelSaveStatus(key, detail = "") {
  const el = document.getElementById("llm-save-status");
  if (!el) return;
  el.dataset.status = key;
  const label = t(`llm.saveStatus.${key}`);
  const text = detail ? `${label}: ${detail}` : label;
  el.textContent = text;
  el.title = detail || label;
}

function markModelConfigUnsaved() {
  setModelSaveStatus("unsaved");
}

/** Non-empty fields only for URLs; models always sent when fields are populated. */
function buildLlmOptionalPayload() {
  const out = {};
  const u = _cfgVal("cfg-llm-base-url");
  if (u) {
    out.llm_base_url = u;
    out.fast_llm_base_url = u;
  }

  const key = _cfgVal("cfg-llm-api-key");
  if (key) out.llm_api_key = key;

  const pm = _cfgVal("cfg-llm-model");
  if (pm) {
    out.llm_model = pm;
    out.fast_llm_model = pm;
  }

  const am = {};
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    const k = sel.dataset.agentKey;
    const v = sel.value?.trim();
    if (k && v) am[k] = v;
  });
  if (Object.keys(am).length) out.agent_models = am;

  return Object.keys(out).length ? out : undefined;
}

function saveModelConfig() {
  try {
    applySavedModelToAgentSelects(_cfgVal("cfg-llm-model"));
    const j = buildLlmOptionalPayload();
    if (j) {
      j.model_options = savedModelOptionsForStorage(j);
      localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(j));
    } else {
      localStorage.removeItem(LLM_STORAGE_KEY);
    }
    _currentModelConfigBaseModel = j?.llm_model || "";
    void loadModelConfigUi("saved");
  } catch {
    setModelSaveStatus("error");
  }
}

async function testModelConnection() {
  setModelSaveStatus("testing");
  try {
    const payload = buildLlmOptionalPayload() || {};
    const r = await fetch("/api/config/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let body = {};
    try {
      body = await r.json();
    } catch {
      /* ignore */
    }
    if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
    setModelSaveStatus(body.ok ? "connected" : "testFailed", body.message || "");
  } catch (err) {
    setModelSaveStatus("testFailed", err?.message || String(err));
  }
}

async function resetModelConfig() {
  try {
    localStorage.removeItem(LLM_STORAGE_KEY);
  } catch {
    /* ignore */
  }
  await loadModelConfigUi();
  setModelSaveStatus("reset");
}

async function loadModelConfigUi(statusKey = "loaded") {
  let server = {};
  try {
    const r = await fetch("/api/config");
    if (r.ok) server = await r.json();
  } catch {
    /* ignore */
  }
  let saved = {};
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY);
    if (raw) saved = JSON.parse(raw);
  } catch {
    /* ignore */
  }
  const merged = { ...server, ...saved };
  const opts = mergeModelOptions(server.model_options, saved.model_options, saved.llm_model);
  const defaults = merged.default_agent_models && typeof merged.default_agent_models === "object"
    ? merged.default_agent_models
    : {};

  renderModelNameInput(
    document.getElementById("cfg-llm-model"),
    opts,
    server.llm_model,
    saved.llm_model
  );
  const selectedModel = saved.llm_model || opts[0] || server.llm_model || "";
  _currentModelConfigBaseModel = selectedModel;
  renderAgentModelSelects(opts, defaults, saved.agent_models, selectedModel);

  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el && v != null && v !== "") el.value = v;
  };
  set("cfg-llm-base-url", merged.llm_base_url);
  set("cfg-llm-api-key", saved.llm_api_key);

  setModelSaveStatus(statusKey);

  if (!loadModelConfigUi._inputsWired) {
    loadModelConfigUi._inputsWired = true;
    for (const id of ["cfg-llm-base-url", "cfg-llm-api-key"]) {
      document.getElementById(id)?.addEventListener("input", markModelConfigUnsaved);
    }
    document.getElementById("cfg-llm-model")?.addEventListener("input", (ev) => {
      markModelConfigUnsaved();
    });
    document.getElementById("llm-save-config")?.addEventListener("click", saveModelConfig);
    document.getElementById("llm-test-config")?.addEventListener("click", testModelConnection);
    document.getElementById("llm-reset-config")?.addEventListener("click", resetModelConfig);
  }
}

function sidebarWidthMax() {
  return Math.min(Math.floor(window.innerWidth * 0.5), SIDEBAR_MAX_PX);
}

function applySidebarWidth(px) {
  const max = sidebarWidthMax();
  const w = Math.round(Math.min(Math.max(px, SIDEBAR_MIN_PX), max));
  document.documentElement.style.setProperty("--sidebar-width", `${w}px`);
  try {
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(w));
  } catch {
    /* ignore */
  }
  return w;
}

function initSidebarResize() {
  const handle = document.getElementById("sidebar-resize-handle");
  const aside = document.querySelector(".agent-sidebar");
  if (!handle || !aside) return;

  try {
    const saved = localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    if (saved != null) {
      const n = parseInt(saved, 10);
      if (!Number.isNaN(n)) applySidebarWidth(n);
    }
  } catch {
    /* ignore */
  }

  window.addEventListener("resize", () => {
    const cur = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width").trim() || "260"
    );
    if (!Number.isNaN(cur)) applySidebarWidth(cur);
  });

  let startX = 0;
  let startWidth = 0;

  function onPointerMove(e) {
    const dx = e.clientX - startX;
    applySidebarWidth(startWidth + dx);
  }

  function onPointerUp(e) {
    try {
      handle.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    document.body.classList.remove("sidebar-resizing");
    document.body.style.userSelect = "";
  }

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (window.matchMedia("(max-width: 900px)").matches) return;
    e.preventDefault();
    startX = e.clientX;
    startWidth = aside.getBoundingClientRect().width;
    handle.setPointerCapture(e.pointerId);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.body.classList.add("sidebar-resizing");
    document.body.style.userSelect = "none";
  });

  handle.addEventListener("keydown", (e) => {
    if (window.matchMedia("(max-width: 900px)").matches) return;
    let delta = 0;
    if (e.key === "ArrowLeft") delta = -12;
    else if (e.key === "ArrowRight") delta = 12;
    else return;
    e.preventDefault();
    const cur = aside.getBoundingClientRect().width;
    applySidebarWidth(cur + delta);
  });
}

let _reviewStartTime = null;
let _currentActiveAgent = null;

function fmtDuration(totalSecs) {
  if (totalSecs < 60) return t("common.durationSeconds", { seconds: totalSecs });
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  if (s > 0) {
    return t("common.durationMinutesSeconds", { minutes: m, seconds: s });
  }
  return t("common.durationMinutes", { minutes: m });
}

function escapeHtml(s) {
  if (s == null || s === "") return "";
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

function mergeAgentOutput(existing, incoming) {
  if (existing && typeof existing === "object" && !Array.isArray(existing)
      && incoming && typeof incoming === "object" && !Array.isArray(incoming)) {
    return { ...existing, ...incoming };
  }
  return incoming;
}

function setAgentOutput(agent, output, updatedAt = "") {
  _agentOutputs[agent] = mergeAgentOutput(_agentOutputs[agent], output);
  if (updatedAt) currentAgentOutputUpdatedAt[agent] = updatedAt;
}

function applySnapshotAgentOutputs(agentOutputs, outputUpdatedAt) {
  if (!agentOutputs || typeof agentOutputs !== "object") return;
  const tsMap = outputUpdatedAt && typeof outputUpdatedAt === "object" ? outputUpdatedAt : {};
  for (const [agent, payload] of Object.entries(agentOutputs)) {
    setAgentOutput(agent, payload, String(tsMap[agent] || ""));
    if (AGENT_CARD_NAMES.has(agent)) renderCardOutput(agent, _agentOutputs[agent]);
  }
  if (_drawerOpen && _drawerAgent) renderDrawer(_drawerAgent);
}

async function syncReviewSnapshot(reviewId, options = {}) {
  if (!reviewId) return;
  const { silent = true } = options;
  try {
    const res = await fetch(`/api/review/${reviewId}/snapshot`);
    if (!res.ok) throw new Error(`snapshot ${res.status}`);
    const data = await res.json();
    applySnapshotAgentOutputs(data.agent_outputs, data.agent_output_updated_at);
    if (data.status === "stopped") {
      setGlobalStatus("stopped");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.reviewStopped"), false);
    } else if (data.status === "done") {
      setGlobalStatus("done");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      await renderFinalResultOnce({
        output: data.agent_outputs?.manager,
        reviewId,
      });
    }
    if (!silent && _drawerOpen && _drawerAgent) renderDrawer(_drawerAgent);
    return data;
  } catch (err) {
    if (!silent) {
      console.warn("[analysis trace snapshot sync failed]", err);
    }
    return null;
  }
}

function showToast(message, isError = false, duration = 5200) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const existingOverlay = document.querySelector(".toast-overlay");
  if (existingOverlay) existingOverlay.remove();
  const toastEl = document.createElement("div");
  toastEl.className = `toast${isError ? " error" : ""}`;
  toastEl.setAttribute("role", isError ? "alertdialog" : "alert");
  if (isError) toastEl.setAttribute("aria-modal", "true");

  function fadeOutAndRemove() {
    const overlayEl = document.querySelector(".toast-overlay");
    if (overlayEl) {
      overlayEl.style.opacity = "0";
      overlayEl.style.transition = "opacity 0.3s";
    }
    toastEl.style.opacity = "0";
    toastEl.style.transition = "opacity 0.3s";
    setTimeout(() => {
      toastEl.remove();
      if (overlayEl) overlayEl.remove();
      if (isError) {
        document.removeEventListener("keydown", onErrorDismissHotkey);
      }
    }, 320);
  }

  function onErrorDismissHotkey(e) {
    if (e.key === "Escape") {
      fadeOutAndRemove();
    }
  }

  if (isError) {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    document.body.appendChild(overlay);

    const msgEl = document.createElement("span");
    msgEl.className = "toast-msg";
    msgEl.textContent = message;
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "toast-dismiss";
    dismiss.setAttribute("aria-label", t("buttons.close"));
    dismiss.textContent = "×";
    dismiss.addEventListener("click", fadeOutAndRemove);
    toastEl.appendChild(msgEl);
    toastEl.appendChild(dismiss);
    document.addEventListener("keydown", onErrorDismissHotkey);
    requestAnimationFrame(() => dismiss.focus());
  } else {
    toastEl.textContent = message;
    setTimeout(fadeOutAndRemove, duration);
  }

  document.body.appendChild(toastEl);
}

function dataLoaderDetail(key, vars = {}) {
  return { key, vars };
}

function currentDataLoaderDetailInput() {
  if (currentDataLoaderUi.detailKey) {
    return dataLoaderDetail(currentDataLoaderUi.detailKey, currentDataLoaderUi.detailVars);
  }
  return currentDataLoaderUi.detailText;
}

function resolveDataLoaderDetail(detail) {
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.key) {
    return t(detail.key, detail.vars || {});
  }
  return String(detail || "").trim();
}

function normalizeDataLoaderDetail(detail) {
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.key) {
    return {
      detailKey: detail.key,
      detailVars: detail.vars || {},
      detailText: "",
    };
  }
  return {
    detailKey: "",
    detailVars: {},
    detailText: String(detail || "").trim(),
  };
}

function recordDataLoaderEvent(state, detail) {
  const text = String(detail || "").trim() || t("dataLoader.statusUpdated");
  const last = dataLoaderHistory[0];
  if (last && last.state === state && last.detail === text) {
    return;
  }
  dataLoaderHistory.unshift({
    state,
    detail: text,
    at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  });
  if (dataLoaderHistory.length > DATA_LOADER_HISTORY_MAX) {
    dataLoaderHistory.length = DATA_LOADER_HISTORY_MAX;
  }
  renderDataLoaderHistory();
}

function renderDataLoaderHistory() {
  const list = document.getElementById("data-loader-history");
  if (!list) return;
  if (dataLoaderHistory.length === 0) {
    list.innerHTML = `<li><span>--:--:--</span>${escapeHtml(t("dataLoader.noDetailedEventsYet"))}</li>`;
    return;
  }
  list.innerHTML = dataLoaderHistory
    .map((item) => `<li><span>${escapeHtml(item.at)}</span>${escapeHtml(item.detail)}</li>`)
    .join("");
}

function setDataLoaderExpanded(expanded) {
  const toggle = document.getElementById("data-loader-toggle");
  const body = document.getElementById("data-loader-expanded");
  if (!toggle || !body) return;
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  const label = toggle.querySelector("span");
  if (label) label.textContent = expanded ? t("dataLoader.hideDetails") : t("dataLoader.showDetails");
  body.classList.toggle("hidden", !expanded);
  if (expanded) renderDataLoaderHistory();
}

function toggleDataLoaderExpanded() {
  const toggle = document.getElementById("data-loader-toggle");
  if (!toggle) return;
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  setDataLoaderExpanded(!expanded);
}

function setDataLoaderStatus(state, detail = "", allowRetry = false, options = {}) {
  const { recordHistory = true } = options;
  const badge = document.getElementById("data-loader-status");
  const detailEl = document.getElementById("data-loader-detail");
  const retryBtn = document.getElementById("retry-review-btn");
  const detailState = normalizeDataLoaderDetail(detail);
  currentDataLoaderUi = { state, ...detailState, allowRetry };
  const text = resolveDataLoaderDetail(detail) || t("dataLoader.waitingHistoryStatus");
  if (badge) {
    const labels = {
      idle: t("status.idle"),
      running: t("status.running"),
      done: t("status.done"),
      error: t("status.error"),
    };
    badge.className = `badge badge-${state}`;
    badge.textContent = labels[state] || state;
  }
  if (detailEl) {
    detailEl.textContent = text;
  }
  if (retryBtn) {
    retryBtn.classList.toggle("hidden", !allowRetry);
    retryBtn.disabled = !allowRetry;
  }
  if (recordHistory) {
    recordDataLoaderEvent(state, text);
  }
}

function isDataLoaderError(message) {
  return DATA_LOADER_ERROR_RE.test(String(message || ""));
}

function formatDataLoaderError(message) {
  const text = String(message || "").trim();
  const analogMissing = text.match(/missing portfolio history for analog matching:\s*(.+)$/i);
  if (analogMissing) {
    return t("dataLoader.missingAnalogHistory", { items: analogMissing[1] });
  }
  const holdingsMissing = text.match(/missing price history for holdings:\s*(.+)$/i);
  if (holdingsMissing) {
    return t("dataLoader.missingHoldingsHistory", { items: holdingsMissing[1] });
  }
  return text || t("dataLoader.historicalDataLoaderFailed");
}

function compactStatusDetail(message, fallback = t("dataLoader.reviewFailed")) {
  const text = String(message || "").replace(/\s+/g, " ").trim() || fallback;
  if (text.length <= STATUS_DETAIL_MAX_CHARS) return text;
  return `${text.slice(0, STATUS_DETAIL_MAX_CHARS - 1)}…`;
}

function cloneReviewBody(body) {
  return JSON.parse(JSON.stringify(body));
}

async function retryLastReview() {
  if (!lastStartBody) {
    showToast(t("review.retryUnavailable"), true);
    return;
  }
  await runReviewWithBody(cloneReviewBody(lastStartBody), { fromRetry: true });
}

function fmtUsd(n) {
  return formatCurrency(n);
}

function fmtPrice(n) {
  return formatPrice(n);
}

function fmtPctDisplay(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`.replace(/^\+-/, "-");
}

function toFiniteNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v, digits = 2, signed = false) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const sign = signed && n >= 0 ? "+" : "";
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`.replace(/^\+-/, "-");
}

function fmtPctFromRatio(v, digits = 1) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const pct = n * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${formatNumber(Math.abs(pct), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`.replace(/^\+-/, "-");
}

function fmtPctAbsFromRatio(v, digits = 1) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  return `${formatNumber(Math.abs(n * 100), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

function truncateText(value, limit = 140) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function setButtonBusy(btn, busy, busyLabel) {
  if (!btn) return;
  if (!btn.dataset.labelIdle) btn.dataset.labelIdle = btn.textContent.trim();
  if (busy) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.textContent = busyLabel || btn.dataset.labelBusy || btn.dataset.labelIdle;
    if (busyLabel) btn.dataset.labelBusy = busyLabel;
    return;
  }
  btn.textContent = btn.dataset.labelIdle || btn.textContent;
  btn.removeAttribute("aria-busy");
  btn.disabled = false;
}

function setStopButtonRunning(running) {
  const stopBtn = document.getElementById("stop-btn");
  if (!stopBtn) return;
  stopBtn.disabled = !running;
  stopBtn.removeAttribute("aria-busy");
  stopBtn.textContent = t("buttons.stopReview");
}

function getLastPrice(wrap) {
  const pe = wrap.querySelector('[data-ro="price"]');
  if (!pe) return NaN;
  const d = pe.dataset.lastPrice;
  if (d != null && d !== "") {
    const v = parseFloat(d);
    return Number.isNaN(v) ? NaN : v;
  }
  return NaN;
}

function getQuoteAction(wrap, key, fallback) {
  const pe = wrap.querySelector('[data-ro="price"]');
  if (!pe) return fallback;
  const v = parseFloat(pe.dataset[key]);
  return Number.isNaN(v) ? fallback : v;
}

function getCashDollarsInput() {
  const v = parseFloat(document.getElementById("p-cash")?.value);
  if (Number.isNaN(v) || v < 0) return 0;
  return v;
}

/** Sum of quantity × last price for all rows (for cash weight and NAV). */
function sumPositionMarketValues() {
  let sum = 0;
  for (const wrap of document.querySelectorAll("#positions-body .position-row-wrap")) {
    sum += getPositionMarketValue(wrap);
  }
  return sum;
}

function getPositionMarketValue(wrap) {
  const q = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
  const cur = getLastPrice(wrap);
  const qtyOk = !Number.isNaN(q) && q !== 0;
  const curOk = !Number.isNaN(cur);
  return qtyOk && curOk ? q * cur : 0;
}

function refreshMetrics(wrap) {
  const q = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
  const cur = getLastPrice(wrap);
  const valEl = wrap.querySelector('[data-ro="value"]');

  const qtyOk = !Number.isNaN(q) && q !== 0;
  const curOk = !Number.isNaN(cur);

  if (valEl) {
    valEl.classList.remove("muted");
    if (qtyOk && curOk) {
      valEl.textContent = fmtUsd(q * cur);
    } else {
      valEl.textContent = "—";
      valEl.classList.add("muted");
    }
  }
}

function scheduleQuoteFetch(wrap) {
  const prev = quoteTimers.get(wrap);
  if (prev) clearTimeout(prev);
  quoteTimers.set(wrap, setTimeout(() => fetchQuoteForCard(wrap), 420));
}

async function fetchQuoteForCard(wrap) {
  const tickerInput = wrap.querySelector('[data-field="ticker"]');
  const priceEl = wrap.querySelector('[data-ro="price"]');
  const m1 = wrap.querySelector('[data-ro="ret-1m"]');
  const m1y = wrap.querySelector('[data-ro="ret-1y"]');
  if (!tickerInput || !priceEl || !m1 || !m1y) return;

  const ticker = tickerInput.value.trim().toUpperCase();
  if (!ticker) {
    wrap.dataset.quoteState = "idle";
    delete priceEl.dataset.lastPrice;
    delete priceEl.dataset.dividend;
    delete priceEl.dataset.split;
    priceEl.textContent = "—";
    priceEl.classList.add("muted");
    m1.textContent = "—";
    m1y.textContent = "—";
    m1.classList.add("muted");
    m1y.classList.add("muted");
    refreshMetrics(wrap);
    return;
  }

  wrap.dataset.quoteState = "loading";
  priceEl.textContent = "…";
  priceEl.classList.add("muted");
  m1.textContent = "…";
  m1y.textContent = "…";
  m1.classList.add("muted");
  m1y.classList.add("muted");

  try {
    const params = new URLSearchParams();
    const reviewDate = document.getElementById("p-date")?.value;
    if (reviewDate) params.set("actions_start", reviewDate);
    const qs = params.toString();
    const res = await fetch(`/api/market/quote/${encodeURIComponent(ticker)}${qs ? `?${qs}` : ""}`);
    if (!res.ok) throw new Error("bad");
    const j = await res.json();
    const px = Number(j.current_price);
    if (Number.isFinite(px)) {
      priceEl.dataset.lastPrice = String(px);
      priceEl.textContent = fmtPrice(px);
      priceEl.classList.remove("muted");
      wrap.dataset.quoteState = "ready";
    } else {
      delete priceEl.dataset.lastPrice;
      priceEl.textContent = "—";
      priceEl.classList.add("muted");
      wrap.dataset.quoteState = "error";
    }

    const dividend = Number(j.dividend);
    priceEl.dataset.dividend = Number.isFinite(dividend) ? String(dividend) : "0";
    const split = Number(j.split);
    priceEl.dataset.split = Number.isFinite(split) && split > 0 ? String(split) : "1";

    const r1 = Number(j.change_1m_pct);
    const r1y = Number(j.change_1y_pct);
    m1.textContent = Number.isFinite(r1) ? fmtPctDisplay(r1) : "—";
    m1y.textContent = Number.isFinite(r1y) ? fmtPctDisplay(r1y) : "—";
    m1.classList.toggle("positive", r1 > 0);
    m1.classList.toggle("negative", r1 < 0);
    m1y.classList.toggle("positive", r1y > 0);
    m1y.classList.toggle("negative", r1y < 0);
    m1.classList.remove("muted");
    m1y.classList.remove("muted");
  } catch {
    wrap.dataset.quoteState = "error";
    delete priceEl.dataset.lastPrice;
    delete priceEl.dataset.dividend;
    delete priceEl.dataset.split;
    priceEl.textContent = "—";
    priceEl.classList.add("muted");
    m1.textContent = "—";
    m1y.textContent = "—";
    m1.classList.remove("positive", "negative");
    m1y.classList.remove("positive", "negative");
    m1.classList.add("muted");
    m1y.classList.add("muted");
  }
  refreshMetrics(wrap);
  updateWeightSummary();
}

async function refreshAllQuotes() {
  const btn = document.getElementById("refresh-quotes-btn");
  const wraps = Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
  if (wraps.length === 0) {
    showToast(t("review.refreshQuotesAddPosition"), true);
    return;
  }
  const hasTicker = wraps.some((w) => w.querySelector('[data-field="ticker"]')?.value?.trim());
  if (!hasTicker) {
    showToast(t("review.refreshQuotesEnterTicker"), true);
    return;
  }
  setButtonBusy(btn, true, t("buttons.refreshMarketData"));
  try {
    await Promise.all(wraps.map((w) => fetchQuoteForCard(w)));
    showToast(t("review.marketDataRefreshed"));
  } finally {
    setButtonBusy(btn, false);
    refreshPositionsState();
  }
}

function positionRowsMissingReadyQuotes() {
  return Array.from(document.querySelectorAll("#positions-body .position-row-wrap"))
    .filter((wrap) => {
      const ticker = wrap.querySelector('[data-field="ticker"]')?.value?.trim();
      if (!ticker) return false;
      const quantity = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
      if (Number.isNaN(quantity) || quantity <= 0) return false;
      return Number.isNaN(getLastPrice(wrap));
    })
    .map((wrap) => wrap.querySelector('[data-field="ticker"]')?.value?.trim()?.toUpperCase())
    .filter(Boolean);
}

function refreshPositionsState() {
  const rows = Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
  const total = rows.length;
  const noteCount = rows.filter(
    (wrap) => wrap.querySelector('[data-field="entry_thesis"]')?.value?.trim(),
  ).length;

  const meta = document.getElementById("positions-meta");
  if (meta) {
    if (total === 0) {
      meta.textContent = t("positions.metaNone");
    } else {
      const positionLabel = total === 1 ? t("positions.positionSingular") : t("positions.positionPlural");
      const noteLabel = noteCount === 1 ? t("positions.noteSingular") : t("positions.notePlural");
      meta.textContent = t("positions.metaLoaded", {
        count: total,
        noteCount,
        positionLabel,
        noteLabel,
      });
    }
  }

  const empty = document.getElementById("positions-empty-state");
  const scroll = document.querySelector("#positions-section .positions-scroll");
  if (empty) empty.classList.toggle("hidden", total !== 0);
  if (scroll) scroll.classList.toggle("hidden", total === 0);

  const refreshBtn = document.getElementById("refresh-quotes-btn");
  if (refreshBtn && refreshBtn.getAttribute("aria-busy") !== "true") {
    refreshBtn.disabled = total === 0;
  }
}

function updateWeightSummary() {
  const cashD = getCashDollarsInput();
  const sumPos = sumPositionMarketValues();
  const nav = sumPos + cashD;
  const impliedCashPct = nav > 0 ? (cashD / nav) * 100 : 0;
  let sumW = 0;

  for (const card of document.querySelectorAll("#positions-body .position-row-wrap")) {
    const wEl = card.querySelector('[data-ro="weight"]');
    if (!wEl) continue;
    const positionValue = getPositionMarketValue(card);
    const pct = nav > 0 ? (positionValue / nav) * 100 : 0;
    wEl.textContent = `${formatNumber(pct, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
    wEl.classList.toggle("muted", nav <= 0);
    sumW += pct;
  }

  const fmt = (n) => `${formatNumber(n, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  const posEl = document.getElementById("weight-positions");
  const cashOut = document.getElementById("weight-cash");
  const totEl = document.getElementById("weight-total");
  if (posEl) posEl.textContent = fmt(sumW);
  if (cashOut) cashOut.textContent = fmtUsd(cashD);
  if (totEl) {
    totEl.textContent = fmtUsd(nav);
    totEl.className = "";
    const target = sumW + impliedCashPct;
    if (Math.abs(target - 100) > 2) totEl.classList.add("bad");
    else if (Math.abs(target - 100) > 0.5) totEl.classList.add("warn");
  }
  refreshPositionsState();
}

function wirePositionRow(wrap) {
  wrap.querySelector('[data-field="quantity"]')?.addEventListener("input", () => refreshMetrics(wrap));

  const tickerEl = wrap.querySelector('[data-field="ticker"]');
  if (tickerEl) {
    tickerEl.addEventListener("blur", () => fetchQuoteForCard(wrap));
    tickerEl.addEventListener("input", () => scheduleQuoteFetch(wrap));
  }

  const toggle = wrap.querySelector(".btn-assert-toggle");
  const panel = wrap.querySelector(".position-assertion-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      const open = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !open);
      wrap.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "▾" : "▸";
    });
  }

  wrap.querySelector(".delete-btn")?.addEventListener("click", () => {
    wrap.remove();
    updateWeightSummary();
  });

  refreshMetrics(wrap);
}

function wireAgentCardInteractions(card, agent) {
  const header = card?.querySelector(".card-header");
  if (!header) return;
  header.setAttribute("role", "button");
  header.setAttribute("tabindex", "0");
  header.setAttribute("aria-haspopup", "dialog");
  header.setAttribute("aria-controls", "agent-drawer");
  header.onclick = () => openDrawer(agent);
  header.onkeydown = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    openDrawer(agent);
  };
}

function localizeAgentCards() {
  document.querySelectorAll(".agent-card").forEach((card) => {
    const agent = card.dataset.agent;
    const plan = getAgentPlan(agent);
    const labelEl = card.querySelector(".agent-label");
    if (labelEl) labelEl.textContent = plan.label;
    const statusEl = card.querySelector(".agent-status-label");
    if (statusEl) {
      const state = card.classList.contains("running") ? "running"
        : card.classList.contains("done") ? "done"
        : card.classList.contains("error") ? "error"
        : card.classList.contains("waiting") ? "waiting"
        : "idle";
      statusEl.textContent = AGENT_STATUS_LABELS[state]?.() ?? state;
    }
  });
}

function applyLocaleToLiveUi() {
  applyTranslations(document);
  applyTranslations(document.getElementById("positions-body") || document);
  document.querySelectorAll("button").forEach((btn) => {
    if (!btn.disabled || btn.getAttribute("aria-busy") !== "true") {
      btn.dataset.labelIdle = btn.textContent.trim();
    }
  });
  localizeAgentCards();
  refreshPositionsState();
  updateWeightSummary();
  setGlobalStatus(currentGlobalStatusState);
  setDataLoaderStatus(
    currentDataLoaderUi.state,
    currentDataLoaderDetailInput(),
    currentDataLoaderUi.allowRetry,
    { recordHistory: false },
  );
  initSavedReview();
  renderHistoryList();
  if (currentResultsView) {
    applyResultsFromData(
      currentResultsView.manager,
      currentResultsView.validation,
      currentResultsView.bundle || currentResultsView.agentOutputs,
    );
  }
  if (_drawerOpen && _drawerAgent) {
    renderDrawer(_drawerAgent);
  }
  loadModelConfigUi();
}

document.addEventListener("DOMContentLoaded", async () => {
  await initI18n();
  applyLocaleToLiveUi();
  const weightCol = document.querySelector(".positions-head-row span:nth-child(3)");
  if (weightCol) weightCol.textContent = t("positions.weightPercent");

  updateWeightSummary();

  document.getElementById("add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("empty-add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("restore-sample-btn")?.addEventListener("click", restoreDefaultPositions);
  document.getElementById("import-portfolio-btn")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    document.getElementById("portfolio-csv-input")?.click();
  });
  document.getElementById("portfolio-csv-input")?.addEventListener("change", handlePortfolioCsvImport);
  document.getElementById("save-portfolio-btn")?.addEventListener("click", savePortfolioCsv);
  document.getElementById("refresh-quotes-btn")?.addEventListener("click", () => refreshAllQuotes());
  document.getElementById("start-btn")?.addEventListener("click", startReview);
  document.getElementById("stop-btn")?.addEventListener("click", stopReview);
  document.getElementById("retry-review-btn")?.addEventListener("click", retryLastReview);
  document.getElementById("data-loader-toggle")?.addEventListener("click", toggleDataLoaderExpanded);
  document.getElementById("open-saved-review")?.addEventListener("click", openSavedReviewFromStorage);
  document.getElementById("open-review-history")?.addEventListener("click", showHistoryModal);
  document.getElementById("open-llm-config")?.addEventListener("click", showLlmConfigModal);
  document.getElementById("locale-switcher")?.addEventListener("change", async (e) => {
    await setLocale(e.target.value);
  });
  document.getElementById("llm-config-modal-close")?.addEventListener("click", hideLlmConfigModal);
  document.getElementById("llm-config-modal-backdrop")?.addEventListener("click", hideLlmConfigModal);
  document.getElementById("history-modal-close")?.addEventListener("click", hideHistoryModal);
  document.getElementById("history-modal-backdrop")?.addEventListener("click", hideHistoryModal);
  document.getElementById("drawer-raw-toggle")?.addEventListener("change", (e) => {
    drawerRawMode = Boolean(e.target?.checked);
    if (_drawerOpen && _drawerAgent) renderDrawer(_drawerAgent);
  });
  document.getElementById("results-modal-close")?.addEventListener("click", hideResultsModal);
  document.getElementById("results-modal-backdrop")?.addEventListener("click", hideResultsModal);
  wireShareControls();
  wireAgentAnalysisControls();
  document.getElementById("agent-summary-dismiss")?.addEventListener("click", dismissAgentSummary);
  document.getElementById("agent-summary-close")?.addEventListener("click", dismissAgentSummary);
  document.getElementById("drawer-close-btn")?.addEventListener("click", closeDrawer);
  document.getElementById("drawer-pin-btn")?.addEventListener("click", togglePin);
  document.getElementById("agent-drawer-backdrop")?.addEventListener("click", closeDrawer);
  document.querySelectorAll(".agent-card").forEach(card => {
    const agent = card.dataset.agent;
    wireAgentCardInteractions(card, agent);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (_drawerOpen) {
      e.preventDefault();
      closeDrawer();
      return;
    }
    const llmModal = document.getElementById("llm-config-modal");
    if (llmModal && !llmModal.classList.contains("hidden")) {
      e.preventDefault();
      hideLlmConfigModal();
      return;
    }
    const historyModal = document.getElementById("history-modal");
    if (historyModal && !historyModal.classList.contains("hidden")) {
      e.preventDefault();
      hideHistoryModal();
      return;
    }
    const modal = document.getElementById("results-modal");
    if (modal && !modal.classList.contains("hidden")) {
      e.preventDefault();
      hideResultsModal();
    }
  });
  onLocaleChange((locale) => {
    const switcher = document.getElementById("locale-switcher");
    if (switcher) switcher.value = locale;
    applyLocaleToLiveUi();
  });
  const switcher = document.getElementById("locale-switcher");
  if (switcher) switcher.value = getLocale();
  initSavedReview();
  initSidebarResize();
  loadModelConfigUi();
  document.getElementById("p-cash")?.addEventListener("input", updateWeightSummary);

  document.getElementById("positions-body")?.addEventListener("input", (e) => {
    if (e.target?.closest?.(".position-row-wrap")) updateWeightSummary();
  });
  document.getElementById("positions-body")?.addEventListener("change", (e) => {
    if (e.target?.closest?.(".position-row-wrap")) updateWeightSummary();
  });

  setDataLoaderExpanded(false);
  setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.waitingHistoryStatus"), false);

  try {
    await loadSamplePortfolio({ silent: true });
  } catch (err) {
    console.error("[sample portfolio load failed]", err);
  }
});

function addRow(data = {}) {
  const grid = document.getElementById("positions-body");
  const wrap = document.createElement("div");
  wrap.className = "position-row-wrap";
  wrap.dataset.quoteState = "idle";

  const tickerValue = escapeHtml(data.ticker);
  const n = escapeHtml(data.name);
  const qty = data.quantity != null && data.quantity !== "" ? escapeHtml(String(data.quantity)) : "";
  const s = escapeHtml(data.sector);
  const thesis = escapeHtml(data.entry_thesis);
  const ac = data.asset_class || "equity";

  wrap.innerHTML = `
    <div class="position-row">
      <input type="text" data-field="ticker" class="pc-ticker" value="${tickerValue}" placeholder="${escapeHtml(t("positions.row.tickerPlaceholder"))}" autocomplete="off" title="${escapeHtml(t("positions.row.tickerTitle"))}" data-i18n-placeholder="positions.row.tickerPlaceholder" data-i18n-title="positions.row.tickerTitle" />
      <input type="text" data-field="name" value="${n}" placeholder="${escapeHtml(t("positions.row.namePlaceholder"))}" title="${escapeHtml(t("positions.row.nameTitle"))}" data-i18n-placeholder="positions.row.namePlaceholder" data-i18n-title="positions.row.nameTitle" />
      <span data-ro="weight" class="row-metric muted" title="${escapeHtml(t("positions.row.weightTitle"))}" data-i18n-title="positions.row.weightTitle">0.0%</span>
      <input type="text" data-field="sector" value="${s}" placeholder="${escapeHtml(t("positions.row.sectorPlaceholder"))}" title="${escapeHtml(t("positions.row.sectorTitle"))}" data-i18n-placeholder="positions.row.sectorPlaceholder" data-i18n-title="positions.row.sectorTitle" />
      <select data-field="asset_class" title="${escapeHtml(t("positions.row.assetTitle"))}" data-i18n-title="positions.row.assetTitle">
        ${["equity", "bond", "commodity", "fx", "crypto"].map(a =>
          `<option value="${a}"${a === ac ? " selected" : ""} data-i18n="positions.row.asset.${a}">${t(`positions.row.asset.${a}`)}</option>`
        ).join("")}
      </select>
      <span data-ro="price" class="row-metric muted" title="${escapeHtml(t("positions.row.priceTitle"))}" data-i18n-title="positions.row.priceTitle">—</span>
      <input type="number" data-field="quantity" step="0.0001" value="${qty}" placeholder="${escapeHtml(t("positions.row.quantityPlaceholder"))}" title="${escapeHtml(t("positions.row.quantityTitle"))}" data-i18n-placeholder="positions.row.quantityPlaceholder" data-i18n-title="positions.row.quantityTitle" />
      <span data-ro="value" class="row-metric muted" title="${escapeHtml(t("positions.row.valueTitle"))}" data-i18n-title="positions.row.valueTitle">—</span>
      <span data-ro="ret-1m" class="row-metric muted" title="${escapeHtml(t("positions.row.month1Title"))}" data-i18n-title="positions.row.month1Title">—</span>
      <span data-ro="ret-1y" class="row-metric muted" title="${escapeHtml(t("positions.row.year1Title"))}" data-i18n-title="positions.row.year1Title">—</span>
      <button type="button" class="btn-assert-toggle" aria-expanded="false" aria-label="${escapeHtml(t("positions.row.showAssertion"))}" title="${escapeHtml(t("positions.row.assertionTitle"))}" data-i18n-aria-label="positions.row.showAssertion" data-i18n-title="positions.row.assertionTitle">▸</button>
      <button type="button" class="delete-btn" aria-label="${escapeHtml(t("positions.row.removePosition"))}" data-i18n-aria-label="positions.row.removePosition">✕</button>
    </div>
    <div class="position-assertion-panel hidden">
      <div class="assertion-inner">
        <span class="assertion-label" data-i18n="positions.row.yourAssertion">${t("positions.row.yourAssertion")}</span>
        <textarea data-field="entry_thesis" rows="3" placeholder="${escapeHtml(t("positions.row.assertionPlaceholder"))}" data-i18n-placeholder="positions.row.assertionPlaceholder">${thesis}</textarea>
      </div>
    </div>
  `;

  grid.appendChild(wrap);
  applyTranslations(wrap);
  wirePositionRow(wrap);
  updateWeightSummary();
}

function parseCsvRows(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  if (inQuotes) throw new Error(t("review.csvUnclosedQuote"));
  if (field || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => String(cell).trim() !== ""));
}

function parsePortfolioCsv(text) {
  const rows = parseCsvRows(text);
  if (rows.length === 0) throw new Error(t("review.csvEmpty"));

  const headers = rows[0].map((value) => String(value || "").replace(/^\uFEFF/, "").trim().toLowerCase());
  const tickerIndex = headers.indexOf("ticker");
  if (tickerIndex === -1) throw new Error(t("review.csvMissingTicker"));

  const objects = rows.slice(1).map((cells) => {
    const obj = {};
    headers.forEach((header, index) => {
      if (!header) return;
      obj[header] = String(cells[index] || "").trim();
    });
    return obj;
  });
  const first = objects[0] || {};
  const positions = objects
    .filter((row) => row.ticker)
    .map((row) => {
      const assetClass = row.asset_class || "equity";
      if (!POSITION_ASSET_CLASSES.includes(assetClass)) {
        throw new Error(t("review.csvInvalidAssetClass", { assetClass }));
      }
      return {
        ticker: row.ticker,
        name: row.name || "",
        sector: row.sector || "",
        asset_class: assetClass,
        quantity: row.quantity || "",
        entry_thesis: row.entry_thesis || "",
      };
    });

  return {
    meta: {
      name: first.portfolio_name || "",
      benchmark: first.benchmark || "",
      cash_usd: first.cash_usd || "0",
      review_date: first.review_date || "",
      context_note: first.context_note || "",
    },
    positions,
  };
}

function applyPortfolioCsv(text) {
  const { meta, positions } = parsePortfolioCsv(text);
  const grid = document.getElementById("positions-body");
  if (!grid) return;

  document.getElementById("p-name").value = meta.name;
  document.getElementById("p-benchmark").value = meta.benchmark;
  document.getElementById("p-cash").value = meta.cash_usd;
  document.getElementById("p-date").value = meta.review_date;
  document.getElementById("p-context").value = meta.context_note;

  grid.innerHTML = "";
  positions.forEach(addRow);
  updateWeightSummary();
  document.querySelectorAll("#positions-body .position-row-wrap").forEach((wrap) => {
    fetchQuoteForCard(wrap);
  });
}

async function loadSamplePortfolio({ silent = false } = {}) {
  const res = await fetch(SAMPLE_PORTFOLIO_CSV_URL);
  if (!res.ok) throw new Error(t("review.sampleLoadError", { status: res.status }));
  applyPortfolioCsv(await res.text());
  if (!silent) showToast(t("review.sampleRestored"));
}

async function restoreDefaultPositions() {
  try {
    await loadSamplePortfolio();
  } catch (err) {
    console.error("[sample portfolio load failed]", err);
    const detail = err instanceof Error ? err.message : String(err);
    showToast(detail, true);
  }
}

async function handlePortfolioCsvImport(event) {
  const input = event.target;
  const file = input?.files?.[0];
  if (!file) return;

  try {
    applyPortfolioCsv(await readPortfolioCsvFile(file));
    showToast(t("review.csvImported", { filename: file.name }));
  } catch (err) {
    console.error("[portfolio csv import failed]", err);
    const detail = err instanceof Error ? err.message : String(err);
    showToast(detail, true);
  } finally {
    input.value = "";
  }
}

function readPortfolioCsvFile(file) {
  if (typeof file.text === "function") return file.text();

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error(t("review.csvReadError")));
    reader.readAsText(file);
  });
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function portfolioCsvFromForm() {
  const meta = {
    portfolio_name: document.getElementById("p-name").value.trim(),
    benchmark: document.getElementById("p-benchmark").value.trim(),
    cash_usd: document.getElementById("p-cash").value.trim(),
    review_date: document.getElementById("p-date").value,
    context_note: document.getElementById("p-context").value.trim(),
  };
  const rows = Array.from(document.querySelectorAll("#positions-body .position-row-wrap")).map((wrap) => ({
    ...meta,
    ticker: wrap.querySelector('[data-field="ticker"]')?.value?.trim().toUpperCase() || "",
    name: wrap.querySelector('[data-field="name"]')?.value?.trim() || "",
    sector: wrap.querySelector('[data-field="sector"]')?.value?.trim() || "",
    asset_class: wrap.querySelector('[data-field="asset_class"]')?.value || "equity",
    quantity: wrap.querySelector('[data-field="quantity"]')?.value?.trim() || "",
    entry_thesis: wrap.querySelector('[data-field="entry_thesis"]')?.value?.trim() || "",
  }));
  if (rows.length === 0) rows.push({ ...meta, ticker: "", name: "", sector: "", asset_class: "", quantity: "", entry_thesis: "" });

  return [
    PORTFOLIO_CSV_COLUMNS.join(","),
    ...rows.map((row) => PORTFOLIO_CSV_COLUMNS.map((column) => csvEscape(row[column])).join(",")),
  ].join("\n") + "\n";
}

function portfolioCsvFilename() {
  const rawName = document.getElementById("p-name").value.trim() || "portfolio";
  const slug = rawName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "portfolio";
  return `${slug}-${new Date().toISOString().slice(0, 10)}.csv`;
}

function savePortfolioCsv() {
  const blob = new Blob([portfolioCsvFromForm()], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = portfolioCsvFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast(t("review.csvSaved"));
}

function buildPortfolio() {
  const reviewDate = document.getElementById("p-date")?.value || "";
  const positions = [];
  let sumPos = 0;
  const rows = Array.from(document.querySelectorAll("#positions-body .position-row-wrap"));
  const cashD = getCashDollarsInput();
  for (const wrap of rows) {
    sumPos += getPositionMarketValue(wrap);
  }
  const nav = sumPos + cashD;
  for (const wrap of rows) {
    const ticker = wrap.querySelector('[data-field="ticker"]')?.value?.trim();
    if (!ticker) continue;

    const num = (sel, fallback = NaN) => {
      const v = parseFloat(wrap.querySelector(sel)?.value);
      return Number.isNaN(v) ? fallback : v;
    };

    const qtyRaw = wrap.querySelector('[data-field="quantity"]')?.value;
    const qtyParsed = parseFloat(qtyRaw);
    const quantity = qtyRaw === "" || Number.isNaN(qtyParsed) ? 0 : qtyParsed;

    let current_price = getLastPrice(wrap);
    if (Number.isNaN(current_price)) current_price = 0;

    const positionValue = quantity * current_price;
    const weight = nav > 0 ? positionValue / nav : 0;

    positions.push({
      ticker: ticker.toUpperCase(),
      name: wrap.querySelector('[data-field="name"]')?.value?.trim() || "",
      weight,
      quantity,
      sector: wrap.querySelector('[data-field="sector"]')?.value?.trim() || "",
      asset_class: wrap.querySelector('[data-field="asset_class"]')?.value || "equity",
      entry_date: reviewDate,
      entry_price: current_price,
      current_price,
      dividend: getQuoteAction(wrap, "dividend", 0),
      split: getQuoteAction(wrap, "split", 1),
      tags: [],
      entry_thesis: wrap.querySelector('[data-field="entry_thesis"]')?.value?.trim() || "",
      country: "US",
    });
  }
  const cash_weight = nav > 0 ? cashD / nav : 0;

  return {
    name: document.getElementById("p-name").value.trim(),
    benchmark: document.getElementById("p-benchmark").value.trim(),
    cash_weight,
    review_date: document.getElementById("p-date").value,
    context_note: document.getElementById("p-context").value.trim(),
    positions,
    base_currency: "USD",
  };
}

async function startReview() {
  const missingQuotes = positionRowsMissingReadyQuotes();
  if (missingQuotes.length > 0) {
    showToast(t("review.marketDataRequired", { tickers: missingQuotes.join(", ") }), true, 9000);
    return;
  }

  const portfolio = buildPortfolio();
  if (portfolio.positions.length === 0) {
    showToast(t("review.addTickerFirst"), true);
    return;
  }

  const startBody = { portfolio, locale: getLocale() };
  const llmPayload = buildLlmOptionalPayload();
  if (llmPayload) startBody.llm = llmPayload;
  lastStartBody = cloneReviewBody(startBody);
  await runReviewWithBody(startBody);
}

async function runReviewWithBody(startBody, options = {}) {
  const fromRetry = Boolean(options.fromRetry);
  resetCards();
  setGlobalStatus("running");
  requestNotifPermission();
  const startBtn = document.getElementById("start-btn");
  setButtonBusy(startBtn, true, t("buttons.runReviewBusy"));
  setStopButtonRunning(true);
  hideResultsModal();
  setDataLoaderStatus(
    "running",
    fromRetry ? dataLoaderDetail("dataLoader.retrying") : dataLoaderDetail("dataLoader.starting"),
    false,
  );

  let res;
  try {
    res = await fetch("/api/review/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(startBody),
    });
  } catch (err) {
    showToast(t("review.networkStartErrorToast"), true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setStopButtonRunning(false);
    setDataLoaderStatus("error", dataLoaderDetail("dataLoader.networkStartError"), true);
    return;
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* ignore */ }
    showToast(t("review.startReviewError", { detail }), true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setStopButtonRunning(false);
    setDataLoaderStatus("error", dataLoaderDetail("review.startReviewError", { detail }), true);
    return;
  }

  const data = await res.json();
  const review_id = data.review_id;
  if (!review_id) {
    showToast(t("review.invalidResponseToast"), true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setStopButtonRunning(false);
    setDataLoaderStatus("error", dataLoaderDetail("dataLoader.missingReviewId"), true);
    return;
  }
  currentReviewId = review_id;
  setDataLoaderStatus("running", dataLoaderDetail("dataLoader.waitingForMarketData"), false);
  subscribeSSE(review_id);
  void syncReviewSnapshot(review_id);
}

async function stopReview() {
  if (!currentReviewId) return;
  const stopBtn = document.getElementById("stop-btn");
  setButtonBusy(stopBtn, true, t("buttons.stopReviewStopping"));
  try {
    const res = await fetch(`/api/review/${currentReviewId}/stop`, { method: "POST" });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch {
        // ignore parse failures
      }
      throw new Error(detail || t("review.stopReviewErrorFallback"));
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    showToast(t("review.stopReviewError", { detail }), true);
    setButtonBusy(stopBtn, false);
    return;
  }
}

function subscribeSSE(reviewId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/review/${reviewId}/stream`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };

  eventSource.onerror = async () => {
    eventSource.close();
    const snapshot = reviewId ? await syncReviewSnapshot(reviewId) : null;
    if (snapshot?.status === "done" || snapshot?.status === "stopped") {
      return;
    }
    if (![t("status.done"), t("status.stopped")].includes(document.getElementById("global-status").textContent)) {
      setGlobalStatus("error");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
    }
  };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "agent_start":
      setCardState(msg.agent, "running");
      if (msg.agent === "data") {
        setDataLoaderStatus("running", dataLoaderDetail("dataLoader.loadingMarketData"), false);
      }
      agentStepProgress[msg.agent] = { active: -1, done: new Set(), labels: {} };
      _currentActiveAgent = msg.agent;
      startElapsedTimer(msg.agent);
      drawerAutoFollow(msg.agent);
      break;

    case "agent_step":
      recordStep(msg.agent, msg.step_index, msg.label);
      refreshDrawer(msg.agent);
      break;

    case "agent_done":
      stopElapsedTimer(msg.agent);
      completeAllSteps(msg.agent);
      setCardState(msg.agent, "done");
      setAgentOutput(msg.agent, msg.output, msg.ts || "");
      renderCardOutput(msg.agent, _agentOutputs[msg.agent]);
      if (msg.agent === "data") {
        setDataLoaderStatus("done", dataLoaderDetail("dataLoader.marketDataLoaded"), false);
      }
      refreshDrawer(msg.agent);
      _currentActiveAgent = null;
      drawerAutoFollowDelayed(msg.agent);
      if (msg.agent === "manager") {
        pendingFinalResult = { output: msg.output, reviewId: currentReviewId };
        void renderFinalResultOnce(pendingFinalResult);
        setGlobalStatus("done");
        setButtonBusy(document.getElementById("start-btn"), false);
        setStopButtonRunning(false);
        sendCompletionNotification();
      }
      break;

    case "agent_summary":
      enqueueAgentSummary(msg);
      break;

    case "heartbeat":
      break;

    case "error":
      {
        markRunningCardsErrored();
        const failureDetail = isDataLoaderError(msg.message)
          ? formatDataLoaderError(msg.message)
          : String(msg.message || t("dataLoader.reviewFailed"));
        setGlobalStatus("error", failureDetail);
        if (_currentActiveAgent) {
          setCardState(_currentActiveAgent, "error", failureDetail);
        }
        setDataLoaderStatus("error", failureDetail, isDataLoaderError(msg.message));
      }
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      console.error("[review error]", msg.message);
      showToast(msg.message || t("dataLoader.reviewFailed"), true, 12000);
      _currentActiveAgent = null;
      break;

    case "stopped":
      setGlobalStatus("stopped");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.reviewStopped"), false);
      if (eventSource) eventSource.close();
      showToast(msg.message || t("review.reviewStopped"));
      break;
  }
}

const AGENT_STATUS_LABELS = {
  idle: () => t("status.idle"),
  running: () => t("status.running"),
  done: () => t("status.done"),
  waiting: () => t("status.waiting"),
  error: () => t("status.error"),
};

function setCardState(agent, state, detail = "") {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  card.className = `agent-card ${state}`;
  const label = card.querySelector(".agent-status-label");
  if (label) {
    const detailText = String(detail || "").trim();
    label.textContent = state === "error" && detailText
      ? compactStatusDetail(detailText)
      : AGENT_STATUS_LABELS[state]?.() ?? state;
    label.title = detailText;
  }
}

function markRunningCardsErrored() {
  document.querySelectorAll(".agent-card.running").forEach((card) => {
    const agent = card.dataset.agent;
    if (!agent) return;
    stopElapsedTimer(agent);
    setCardState(agent, "error");
  });
}

function renderCardOutput(agent, output) {
  _agentOutputs[agent] = output;
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  const body = card.querySelector(".card-body");
  body.innerHTML = agentOutputHtml(agent, output);
  // Auto-reveal completed agent output as a peek (truncated with fade)
  body.classList.remove("hidden");
  body.classList.add("peek");
  body.onclick = (e) => { e.stopPropagation(); openDrawer(agent); };
}

function actionTypeLabel(value) {
  return t(`actionType.${normalizeActionType(value)}`);
}

function priorityLabel(value) {
  return t(`priority.${normalizePriority(value)}`);
}

function portfolioStanceLabel(value) {
  return t(`portfolioStance.${normalizePortfolioStance(value)}`);
}

function hasMeaningfulPortfolioStance(stance) {
  if (!stance || typeof stance !== "object") return false;
  const hasDetail = ["primary_risk", "recommended_posture", "rationale"].some(
    (field) => String(stance[field] || "").trim()
  );
  return (
    hasDetail ||
    normalizePortfolioStance(stance.stance) !== "balanced" ||
    normalizePriority(stance.urgency) !== "watch"
  );
}

function actionScopeLabel(value) {
  return t(`actionScope.${value || "position"}`);
}

function normalizePriority(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return PRIORITY_ALIASES.get(normalized) || "watch";
}

function normalizeActionType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ACTION_TYPE_ALIASES.get(normalized) || "monitor";
}

function normalizePortfolioStance(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return PORTFOLIO_STANCE_ALIASES.get(normalized) || "balanced";
}

function normalizeActionScope(action) {
  const portfolioScopes = new Set(["portfolio", "portfolio-level", "portfolio_level", "book"]);
  const positionScopes = new Set(["position", "ticker", "security", "holding"]);
  const scope = String(action?.scope || "").trim().toLowerCase();
  if (portfolioScopes.has(scope)) return "portfolio";
  if (positionScopes.has(scope)) return "position";
  const position = String(action?.position || "").trim().toLowerCase();
  return position === "portfolio-level" || position === "portfolio_level" ? "portfolio" : "position";
}

function setElementText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text || "";
}

function appendActionDetail(parent, label, value) {
  const text = String(value || "").trim();
  if (!text) return;
  const wrap = document.createElement("div");
  wrap.className = "action-detail-line";
  const strong = document.createElement("strong");
  strong.textContent = label;
  const span = document.createElement("span");
  span.textContent = text;
  wrap.append(strong, span);
  parent.appendChild(wrap);
}

function appendEvidenceList(parent, evidence) {
  const items = Array.isArray(evidence)
    ? evidence.map((item) => String(item || "").trim()).filter(Boolean)
    : String(evidence || "").trim()
      ? [String(evidence).trim()]
      : [];
  if (!items.length) return;

  const wrap = document.createElement("div");
  wrap.className = "action-detail-line action-detail-line--stacked";
  const strong = document.createElement("strong");
  strong.textContent = t("results.supportingEvidence");
  const ul = document.createElement("ul");
  ul.className = "action-evidence-list";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  }
  wrap.append(strong, ul);
  parent.appendChild(wrap);
}

function appendActionDecisionDetails(parent, action) {
  appendActionDetail(parent, t("results.rationale"), action?.rationale);
  appendActionDetail(parent, t("results.riskAddressed"), action?.risk_addressed);
  appendEvidenceList(parent, action?.supporting_evidence);
  appendActionDetail(parent, t("results.revisitTrigger"), action?.revisit_trigger);
  if (!parent.childNodes.length) parent.textContent = "—";
}

function evidenceItems(evidence) {
  return Array.isArray(evidence)
    ? evidence.map((item) => String(item || "").trim()).filter(Boolean)
    : String(evidence || "").trim()
      ? [String(evidence).trim()]
      : [];
}

function appendActionMemoDetail(parent, label, value) {
  const text = String(value || "").trim();
  if (!text) return;
  const wrap = document.createElement("div");
  wrap.className = "action-memo-block";
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = text;
  wrap.append(dt, dd);
  parent.appendChild(wrap);
}

function appendActionEvidenceMemoDetail(parent, evidence) {
  const items = evidenceItems(evidence);
  if (!items.length) return;
  const wrap = document.createElement("div");
  wrap.className = "action-memo-block";
  const dt = document.createElement("dt");
  dt.textContent = t("results.supportingEvidence");
  const dd = document.createElement("dd");
  const ul = document.createElement("ul");
  ul.className = "action-card__evidence";
  for (const item of items.slice(0, 3)) {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  }
  dd.appendChild(ul);
  wrap.append(dt, dd);
  parent.appendChild(wrap);
}

function formatActionTitle(action) {
  if (!action || typeof action !== "object") return t("share.noImmediateAction");
  const actionType = actionTypeLabel(action.action_type);
  const position = String(action.position || "").trim();
  return [actionType, position].filter(Boolean).join(" - ");
}

function renderActionsTable(actions) {
  const tbody = document.getElementById("actions-body");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!actions.length) {
    const tr = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "actions-empty-cell";
    cell.textContent = t("results.noActions");
    tr.appendChild(cell);
    tbody.appendChild(tr);
    return;
  }
  for (const a of actions) {
    const tr = document.createElement("tr");
    const td = (cls, text) => {
      const cell = document.createElement("td");
      if (cls) cell.className = cls;
      cell.textContent = text ?? "—";
      return cell;
    };
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const chip = document.createElement("span");
      const priority = normalizePriority(a.priority);
      chip.className = `table-chip priority-chip priority-${priority}`;
      chip.textContent = priorityLabel(priority);
      cell.appendChild(chip);
      return cell;
    })());
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const chip = document.createElement("span");
      const actionType = normalizeActionType(a.action_type);
      chip.className = `table-chip action-chip action-${actionType}`;
      chip.textContent = actionTypeLabel(actionType);
      cell.appendChild(chip);
      return cell;
    })());
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const scope = document.createElement("span");
      scope.className = "action-scope-label";
      scope.textContent = actionScopeLabel(normalizeActionScope(a));
      const b = document.createElement("b");
      b.textContent = a.position ?? "—";
      cell.append(scope, b);
      return cell;
    })());
    tr.appendChild((() => {
      const cell = document.createElement("td");
      cell.className = "action-decision-cell";
      appendActionDecisionDetails(cell, a);
      return cell;
    })());
    tr.appendChild(td(null, a.size_guidance));
    tr.appendChild(td(null, a.hedge_instrument || "—"));
    tbody.appendChild(tr);
  }
}

function renderActionCards(actions) {
  const list = document.getElementById("actions-list");
  if (!list) return;
  list.innerHTML = "";
  if (!actions.length) {
    const empty = document.createElement("div");
    empty.className = "action-card action-card--empty";
    empty.textContent = t("results.noActions");
    list.appendChild(empty);
    return;
  }
  actions.forEach((action, index) => {
    const priority = normalizePriority(action.priority);
    const actionType = normalizeActionType(action.action_type);
    const article = document.createElement("article");
    article.className = `action-card action-card--${priority}`;

    const top = document.createElement("div");
    top.className = "action-card__top";

    const rank = document.createElement("span");
    rank.className = "action-card__rank";
    rank.textContent = String(index + 1).padStart(2, "0");

    const chips = document.createElement("div");
    chips.className = "action-card__chips";
    const priorityChip = document.createElement("span");
    priorityChip.className = `table-chip priority-chip priority-${priority}`;
    priorityChip.textContent = priorityLabel(priority);
    const actionChip = document.createElement("span");
    actionChip.className = `table-chip action-chip action-${actionType}`;
    actionChip.textContent = actionTypeLabel(actionType);
    chips.append(priorityChip, actionChip);

    const target = document.createElement("div");
    target.className = "action-card__target";
    const scope = document.createElement("span");
    scope.className = "action-scope-label";
    scope.textContent = actionScopeLabel(normalizeActionScope(action));
    const position = document.createElement("strong");
    position.textContent = action.position ?? "—";
    target.append(scope, position);

    const title = document.createElement("p");
    title.className = "action-card__title";
    title.textContent = action.rationale || action.risk_addressed || formatActionTitle(action);
    top.append(rank, chips, target, title);

    const memo = document.createElement("div");
    memo.className = "action-card__memo";
    const riskColumn = document.createElement("dl");
    riskColumn.className = "action-card__memo-col";
    appendActionMemoDetail(riskColumn, t("results.riskAddressed"), action.risk_addressed);
    appendActionEvidenceMemoDetail(riskColumn, action.supporting_evidence);
    const executionColumn = document.createElement("dl");
    executionColumn.className = "action-card__memo-col";
    appendActionMemoDetail(executionColumn, t("results.columns.sizing"), action.size_guidance);
    appendActionMemoDetail(executionColumn, t("results.columns.hedge"), action.hedge_instrument || "—");
    appendActionMemoDetail(executionColumn, t("results.revisitTrigger"), action.revisit_trigger);
    memo.append(riskColumn, executionColumn);

    article.append(top, memo);
    list.appendChild(article);
  });
}

function normalizeSharePrivacyMode(value) {
  const mode = String(value || "").trim().toLowerCase();
  return ["full", "masked", "anonymous"].includes(mode) ? mode : "masked";
}

function firstText() {
  for (const value of arguments) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function firstArrayItem(value, field = "") {
  if (!Array.isArray(value) || !value.length) return "";
  const item = value[0];
  if (field && item && typeof item === "object") return String(item[field] || "").trim();
  return String(item || "").trim();
}

function agentReviewFromView(view, agent, resultField) {
  const viewOutputs = view?.agentOutputs && typeof view.agentOutputs === "object" ? view.agentOutputs : null;
  const outputs = viewOutputs || _agentOutputs;
  const out = outputs?.[agent];
  if (!out || typeof out !== "object") return null;
  const result = out[resultField];
  if (Array.isArray(result)) return result[0] || null;
  return out;
}

function agentReview(agent, resultField) {
  return agentReviewFromView(currentResultsView || {}, agent, resultField);
}

function sortedManagerActions(manager) {
  const priorityOrder = ["urgent", "this-week", "next-review", "watch"];
  const priorityRank = (value) => {
    const idx = priorityOrder.indexOf(normalizePriority(value));
    return idx === -1 ? priorityOrder.length : idx;
  };
  return Array.from(Array.isArray(manager?.actions) ? manager.actions : []).sort(
    (a, b) => priorityRank(a.priority) - priorityRank(b.priority),
  );
}

function formatActionLine(action) {
  if (!action || typeof action !== "object") return t("share.noImmediateAction");
  const actionType = actionTypeLabel(action.action_type);
  const position = String(action.position || "").trim();
  const risk = String(action.risk_addressed || action.rationale || "").trim();
  return [actionType, position, risk].filter(Boolean).join(" - ");
}

function formatWorstReplay(risk, regime, validation) {
  const worst = risk?.worst_scenario;
  if (worst && typeof worst === "object" && String(worst.name || "").trim()) {
    const loss = Number(worst.estimated_portfolio_loss_pct);
    const suffix = Number.isFinite(loss) ? ` (${formatNumber(loss, { maximumFractionDigits: 1 })}%)` : "";
    return `${String(worst.name).trim()}${suffix}`;
  }
  const outcome = regime?.historical_outcome;
  if (
    outcome &&
    typeof outcome === "object" &&
    outcome.runner_available &&
    String(outcome.message || "").trim()
  ) {
    return String(outcome.message).trim();
  }
  return firstArrayItem(validation?.critical_issues, "issue");
}

function collectTickerSymbols(view) {
  const symbols = new Set();
  const add = (value) => {
    const text = String(value || "").trim().toUpperCase();
    if (!text || text === "PORTFOLIO-LEVEL") return;
    if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(text)) symbols.add(text);
  };

  for (const pos of view?.bundle?.portfolio?.positions || []) add(pos?.ticker);
  for (const action of view?.manager?.actions || []) add(action?.position);

  const risk = agentReviewFromView(view, "risk", "risk_results");
  if (risk?.marginal_risk_by_ticker && typeof risk.marginal_risk_by_ticker === "object") {
    Object.keys(risk.marginal_risk_by_ticker).forEach(add);
  }

  return Array.from(symbols);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildTickerPrivacyMap(view, mode) {
  const normalized = normalizeSharePrivacyMode(mode);
  if (normalized === "full") return new Map();

  return new Map(
    collectTickerSymbols(view).map((symbol, index) => {
      const replacement =
        normalized === "anonymous"
          ? `Position ${index + 1}`
          : `${symbol.slice(0, 1)}${"*".repeat(Math.max(3, symbol.length - 1))}`;
      return [symbol, replacement];
    }),
  );
}

function applySharePrivacy(text, view, mode) {
  let out = String(text || "");
  const replacements = Array.from(buildTickerPrivacyMap(view, mode).entries()).sort(
    (a, b) => b[0].length - a[0].length,
  );
  for (const [symbol, replacement] of replacements) {
    out = out.replace(
      new RegExp(`(^|[^A-Za-z0-9.-])(${escapeRegExp(symbol)})(?=$|[^A-Za-z0-9.-])`, "gi"),
      `$1${replacement}`,
    );
  }
  return out;
}

function buildReceiptPlainText(artifact, mode = currentSharePrivacyMode, sourceView = null) {
  const view = sourceView || artifact?.sourceView || currentResultsView || {};
  const receipt = artifact?.receipt || {};
  const lines = [
    "RISK RECEIPT",
    `${t("share.portfolioStance")}: ${receipt.stance || t("share.na")} - ${receipt.urgency || t("share.na")}`,
    `${t("share.hiddenRisk")}: ${receipt.primaryRisk || t("share.na")}`,
  ];
  if (receipt.worstReplay) lines.push(`${t("share.worstReplay")}: ${receipt.worstReplay}`);
  lines.push(`${t("share.topAction")}: ${receipt.topAction || t("share.noImmediateAction")}`);
  lines.push(`${t("share.confidence")}: ${receipt.confidence || t("share.na")}`);
  lines.push("");
  lines.push(t("share.generatedBy"));
  lines.push(t("share.notFinancialAdvice"));
  return applySharePrivacy(lines.join("\n"), view, mode);
}

function escapeXml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wrapReceiptSvgLine(line, maxChars = 82, maxRows = 2) {
  const words = String(line || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [""];

  const rows = [];
  let current = "";
  let overflow = false;
  for (const word of words) {
    if (current && current.length + 1 + word.length <= maxChars) {
      current += ` ${word}`;
      continue;
    }
    if (!current && word.length <= maxChars) {
      current = word;
      continue;
    }
    if (current) {
      rows.push(current);
      current = "";
      if (rows.length >= maxRows) {
        overflow = true;
        break;
      }
    }
    if (word.length > maxChars) {
      rows.push(word.slice(0, Math.max(0, maxChars - 3)) + "...");
      overflow = true;
      if (rows.length >= maxRows) break;
      continue;
    }
    current = word;
  }
  if (!overflow && current) rows.push(current);
  if (rows.length > maxRows) {
    rows.length = maxRows;
    overflow = true;
  }
  if (overflow && rows.length) {
    const last = rows[rows.length - 1].replace(/\s+$/, "");
    rows[rows.length - 1] =
      last.length > maxChars - 3 ? last.slice(0, Math.max(0, maxChars - 3)) + "..." : `${last}...`;
  }
  return rows.slice(0, maxRows);
}

function buildReceiptSvg(artifact, mode = currentSharePrivacyMode) {
  const lines = buildReceiptPlainText(artifact, mode, artifact?.sourceView).split("\n");
  const rows = [];
  for (const line of lines) {
    for (const row of wrapReceiptSvgLine(line)) {
      if (rows.length >= 13) break;
      rows.push(row);
    }
    if (rows.length >= 13) break;
  }
  const textRows = rows.map((line, index) => {
    const y = 46 + index * 28;
    const weight = index === 0 ? 800 : 500;
    const size = index === 0 ? 22 : 15;
    return `<text x="32" y="${y}" font-size="${size}" font-weight="${weight}" fill="#f4efe7">${escapeXml(line)}</text>`;
  });
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="420" viewBox="0 0 900 420">',
    '<rect width="900" height="420" rx="28" fill="#101317"/>',
    '<rect x="18" y="18" width="864" height="384" rx="22" fill="none" stroke="#d4a574" stroke-opacity="0.45" stroke-width="2"/>',
    '<g font-family="JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
    textRows.join(""),
    "</g>",
    "</svg>",
  ].join("");
}

function markdownList(items) {
  const clean = (Array.isArray(items) ? items : []).map((item) => String(item || "").trim()).filter(Boolean);
  return clean.map((item) => `- ${item}`).join("\n");
}

function buildTeardownMemo(artifact, mode = currentSharePrivacyMode, sourceView = null) {
  const view = sourceView || artifact?.sourceView || currentResultsView || {};
  const manager = view.manager || {};
  const validation = view.validation || {};
  const risk = agentReviewFromView(view, "risk", "risk_results");
  const regime = agentReviewFromView(view, "regime", "regime_results");
  const theme = agentReviewFromView(view, "theme", "theme_results");
  const actions = sortedManagerActions(manager);
  const sections = [];

  sections.push("# Portfolio Risk Teardown");
  sections.push("## Receipt\n\n```text\n" + buildReceiptPlainText(artifact, mode, view) + "\n```");

  const stance = manager.portfolio_stance || {};
  const stanceLines = [
    `- Stance: ${portfolioStanceLabel(stance.stance)}`,
    `- Urgency: ${priorityLabel(stance.urgency)}`,
    stance.primary_risk ? `- Primary risk: ${stance.primary_risk}` : "",
    stance.recommended_posture ? `- Recommended posture: ${stance.recommended_posture}` : "",
    stance.rationale ? `- Rationale: ${stance.rationale}` : "",
  ].filter(Boolean);
  if (stanceLines.length) sections.push(`## Portfolio Stance\n\n${stanceLines.join("\n")}`);

  const riskLines = markdownList(
    []
      .concat(risk?.top_risks || [])
      .concat(risk?.concentration_issues || [])
      .concat(risk?.fragilities || []),
  );
  if (riskLines) sections.push(`## Why This Portfolio Can Break\n\n${riskLines}`);

  const regimeLines = markdownList(
    [regime?.summary]
      .concat(regime?.mismatch_drivers || [])
      .concat([regime?.historical_outcome?.message]),
  );
  if (regimeLines) sections.push(`## Regime Fit\n\n${regimeLines}`);

  const themeLines = markdownList(
    [theme?.implicit_portfolio_bet]
      .concat(theme?.synthesis?.dominant_themes || theme?.dominant_themes || [])
      .concat(theme?.crowding_risks || [])
      .concat(theme?.momentum_conflicts || []),
  );
  if (themeLines) sections.push(`## Theme Alignment\n\n${themeLines}`);

  const validationLines = markdownList(
    []
      .concat((validation?.critical_issues || []).map((issue) => issue?.issue || ""))
      .concat(validation?.thesis_breaks || [])
      .concat(validation?.internal_contradictions || []),
  );
  if (validationLines) sections.push(`## Validation Flags\n\n${validationLines}`);

  if (actions.length) {
    sections.push(
      "## Action Plan\n\n" +
        actions
          .map((action) => {
            const bits = [
              `- [${priorityLabel(action.priority)}] ${formatActionLine(action)}`,
              action.size_guidance ? `  - Sizing: ${action.size_guidance}` : "",
              action.revisit_trigger ? `  - Revisit trigger: ${action.revisit_trigger}` : "",
            ].filter(Boolean);
            return bits.join("\n");
          })
          .join("\n"),
    );
  }

  if (manager.do_nothing_case) {
    sections.push(`## Do-Nothing Case\n\n${manager.do_nothing_case}`);
  }

  sections.push(`_${t("share.generatedBy")}. ${t("share.notFinancialAdvice")}._`);
  return applySharePrivacy(sections.join("\n\n"), view, mode);
}

function deriveShareArtifact(manager, validation, bundle = null) {
  const view = {
    manager,
    validation,
    bundle,
    agentOutputs: bundle?.agentOutputs || currentResultsView?.agentOutputs || _agentOutputs,
  };
  const risk = agentReviewFromView(view, "risk", "risk_results");
  const regime = agentReviewFromView(view, "regime", "regime_results");
  const actions = sortedManagerActions(manager);
  const stance = manager?.portfolio_stance || {};
  const topAction = actions[0];
  const confidence = Number(manager?.overall_confidence);
  const generatedAt = bundle?.savedAt || new Date().toISOString();
  const primaryRisk = firstText(
    stance.primary_risk,
    firstArrayItem(validation?.critical_issues, "issue"),
    firstArrayItem(risk?.top_risks),
    manager?.executive_summary,
  );

  const artifact = {
    receipt: {
      stance: portfolioStanceLabel(stance.stance),
      urgency: priorityLabel(stance.urgency || topAction?.priority),
      primaryRisk,
      worstReplay: formatWorstReplay(risk, regime, validation),
      topAction: topAction ? formatActionLine(topAction) : t("share.noImmediateAction"),
      confidence: Number.isFinite(confidence) ? `${Math.round(confidence)}/10` : t("share.na"),
      generatedAt,
      disclaimer: t("share.notFinancialAdvice"),
    },
    memo: {
      markdown: "",
    },
    privacy: {
      mode: currentSharePrivacyMode,
    },
    sourceView: view,
  };
  artifact.memo.markdown = buildTeardownMemo(artifact, currentSharePrivacyMode, view);
  return artifact;
}

function renderShareArtifact() {
  if (!currentResultsView?.manager) return;
  currentShareArtifact = deriveShareArtifact(
    currentResultsView.manager,
    currentResultsView.validation,
    currentResultsView.bundle,
  );
  const view = currentResultsView || {};
  const receipt = currentShareArtifact.receipt;
  setElementText("receipt-stance", applySharePrivacy(receipt.stance, view, currentSharePrivacyMode));
  setElementText("receipt-urgency", ` - ${applySharePrivacy(receipt.urgency, view, currentSharePrivacyMode)}`);
  setElementText("receipt-primary-risk", applySharePrivacy(receipt.primaryRisk || t("share.na"), view, currentSharePrivacyMode));
  setElementText("receipt-worst-replay", applySharePrivacy(receipt.worstReplay || t("share.na"), view, currentSharePrivacyMode));
  setElementText("receipt-top-action", applySharePrivacy(receipt.topAction || t("share.noImmediateAction"), view, currentSharePrivacyMode));
  setElementText("receipt-confidence", receipt.confidence || t("share.na"));
  setElementText("receipt-generated-at", formatSavedAt(receipt.generatedAt));
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

function downloadTextFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function copyRiskReceipt() {
  try {
    if (currentResultsView?.manager || !currentShareArtifact) renderShareArtifact();
    await copyTextToClipboard(buildReceiptPlainText(currentShareArtifact, currentSharePrivacyMode));
    showToast(t("share.copyReceiptSuccess"));
  } catch {
    showToast(t("share.copyReceiptError"), true);
  }
}

function downloadRiskReceipt() {
  try {
    if (currentResultsView?.manager || !currentShareArtifact) renderShareArtifact();
    downloadTextFile(
      "portfolio-risk-receipt.svg",
      buildReceiptSvg(currentShareArtifact, currentSharePrivacyMode),
      "image/svg+xml;charset=utf-8",
    );
  } catch {
    showToast(t("share.downloadReceiptError"), true);
  }
}

async function copyTeardownMemo() {
  try {
    if (currentResultsView?.manager || !currentShareArtifact) renderShareArtifact();
    await copyTextToClipboard(buildTeardownMemo(currentShareArtifact, currentSharePrivacyMode));
    showToast(t("share.copyMemoSuccess"));
  } catch {
    showToast(t("share.copyMemoError"), true);
  }
}

function downloadTeardownMemo() {
  try {
    if (currentResultsView?.manager || !currentShareArtifact) renderShareArtifact();
    downloadTextFile(
      "portfolio-risk-teardown.md",
      buildTeardownMemo(currentShareArtifact, currentSharePrivacyMode),
      "text/markdown;charset=utf-8",
    );
  } catch {
    showToast(t("share.downloadMemoError"), true);
  }
}

function wireShareControls() {
  document.querySelectorAll('input[name="share-privacy"]').forEach((input) => {
    input.addEventListener("change", (event) => {
      currentSharePrivacyMode = normalizeSharePrivacyMode(event.target?.value);
      renderShareArtifact();
    });
  });
  document.getElementById("copy-risk-receipt")?.addEventListener("click", copyRiskReceipt);
  document.getElementById("download-risk-receipt")?.addEventListener("click", downloadRiskReceipt);
  document.getElementById("copy-teardown-memo")?.addEventListener("click", copyTeardownMemo);
  document.getElementById("download-teardown-memo")?.addEventListener("click", downloadTeardownMemo);
}

function severityLabel(value) {
  return t(`severity.${value || "medium"}`);
}

function stateValueLabel(value) {
  return t(`stateValue.${String(value || "").toLowerCase()}`);
}

function agentOutputHtml(agent, out) {
  if (!out) return `<em>${escapeHtml(t("agentOutput.noOutput"))}</em>`;

  const chip = (val, max = 10) => {
    const n = Number(val);
    if (Number.isNaN(n)) return escapeHtml(String(val));
    const cls = n >= 7 ? "chip-green" : n >= 4 ? "chip-yellow" : "chip-red";
    return `<span class="chip ${cls}">${escapeHtml(String(Math.round(n)))}/${max}</span>`;
  };

  switch (agent) {
    case "news": {
      const chunks = [];
      const rawRes = out.news_research_text;
      if (rawRes && String(rawRes).trim()) {
        const s = String(rawRes);
        chunks.push(
          `<b>${escapeHtml(t("agentOutput.news.toolResearchExcerpt"))}</b> ${escapeHtml(s.slice(0, 480))}${s.length > 480 ? "…" : ""}`,
        );
      }
      const data = out.news_review;
      if (!data || typeof data !== "object") {
        return chunks.length ? chunks.join("<br><br>") : `<em>${escapeHtml(t("agentOutput.news.noBriefingYet"))}</em>`;
      }
      const macro = (data.macro_context || "").slice(0, 200);
      const themes = (data.market_themes || []).map(escapeHtml).join(" · ");
      const evts = (data.key_events || []).slice(0, 6).map(escapeHtml).join("; ");
      chunks.push(
        `<b>${escapeHtml(t("agentOutput.news.macro"))}</b> ${escapeHtml(macro)}${macro.length >= 200 ? "…" : ""}`,
        themes ? `<b>${escapeHtml(t("agentOutput.news.themes"))}</b> ${themes}` : "",
        evts ? `<b>${escapeHtml(t("agentOutput.news.keyEvents"))}</b> ${evts}` : "",
        data.summary ? `<b>${escapeHtml(t("agentOutput.news.summary"))}</b> ${escapeHtml(data.summary)}` : "",
      );
      return chunks.filter(Boolean).join("<br><br>");
    }
    case "risk": {
      const data = Array.isArray(out.risk_results) ? out.risk_results[0] : out;
      const fr = (data.fragilities || []).map(f => "  • " + escapeHtml(f)).join("\n");
      const conc = (data.concentration_issues || []).map(escapeHtml).join("; ");
      const fl = data.factor_loadings && typeof data.factor_loadings === "object"
        ? Object.entries(data.factor_loadings)
          .sort((a, b) => Math.abs(Number(b[1]) || 0) - Math.abs(Number(a[1]) || 0))
          .slice(0, 6)
          .map(([k, v]) => `${escapeHtml(k)} ${fmtNum(v, 2, true)}`)
          .join(" · ")
        : "";
      const frc = data.factor_risk_contribution && typeof data.factor_risk_contribution === "object"
        ? Object.entries(data.factor_risk_contribution)
          .sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0))
          .slice(0, 5)
          .map(([k, v]) => `${escapeHtml(k)} ${fmtPctFromRatio(v, 1)}`)
          .join(" · ")
        : "";
      const mrt = data.marginal_risk_by_ticker && typeof data.marginal_risk_by_ticker === "object"
        ? Object.entries(data.marginal_risk_by_ticker)
          .sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0))
          .slice(0, 5)
          .map(([k, v]) => `${escapeHtml(k)} ${fmtPctFromRatio(v, 1)}`)
          .join(" · ")
        : "";
      const tr = (data.top_risks || []).slice(0, 4).map(escapeHtml).join("; ");
      const worst = data.worst_scenario && typeof data.worst_scenario === "object"
        ? `${escapeHtml(data.worst_scenario.name || "")} (${fmtNum(data.worst_scenario.estimated_portfolio_loss_pct, 1, true)}%)`
        : "";
      const scen = (data.scenario_losses || []).slice(0, 4)
        .map((s) => `  • ${escapeHtml(s.scenario || t("agentOutput.risk.scenarioFallback"))}: ${fmtNum(s.estimated_portfolio_loss_pct, 1, true)}%`)
        .join("\n");
      return [
        `${t("agentOutput.risk.riskScore")} ${chip(data.risk_score)}`,
        fl ? `${t("agentOutput.risk.factorLoadings")} ${fl}` : "",
        frc ? `${t("agentOutput.risk.riskContribution")} ${frc}` : "",
        mrt ? `${t("agentOutput.risk.marginalRiskTicker")} ${mrt}` : "",
        tr ? `${t("agentOutput.risk.topRisks")} ${tr}` : "",
        worst ? `${t("agentOutput.risk.worstScenario")} ${worst}` : "",
        scen ? `${t("agentOutput.risk.scenarios")}\n${scen}` : "",
        fr ? `${t("agentOutput.risk.fragilities")}\n${fr}` : "",
        conc ? `${t("agentOutput.risk.concentration")} ${conc}` : "",
        data.summary ? `${t("agentOutput.risk.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "regime": {
      const data = Array.isArray(out.regime_results) ? out.regime_results[0] : out;
      const mm = (data.mismatches || []).map(m => "  • " + escapeHtml(m)).join("\n");
      const md = (data.mismatch_drivers || []).map(m => "  • " + escapeHtml(m)).join("\n");
      const sv = data.state_vector && typeof data.state_vector === "object"
        ? `${escapeHtml(t("agentOutput.regime.stateVector.inflation"))} ${escapeHtml(stateValueLabel(data.state_vector.inflation_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.rates"))} ${escapeHtml(stateValueLabel(data.state_vector.rates_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.growth"))} ${escapeHtml(stateValueLabel(data.state_vector.growth_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.liquidity"))} ${escapeHtml(stateValueLabel(data.state_vector.liquidity))} · ${escapeHtml(t("agentOutput.regime.stateVector.volatility"))} ${escapeHtml(stateValueLabel(data.state_vector.volatility))}`
        : "";
      const hist = data.historical_outcome && typeof data.historical_outcome === "object"
        ? (data.historical_outcome.runner_available === false
          ? `<span class="muted-text">${escapeHtml(t("agentOutput.regime.historicalRunnerOff"))}</span>`
          : `${escapeHtml(t("agentOutput.regime.historicalAnalogs"))} ${escapeHtml(data.historical_outcome.message || "")}`)
        : "";
      const fitNotes = (data.fit_notes || []).map(escapeHtml).join("; ");
      return [
        `${t("agentOutput.regime.regime")} <b>${escapeHtml(data.current_regime)}</b>`,
        sv ? `${t("agentOutput.regime.state")} ${sv}` : "",
        `${t("agentOutput.regime.fit")} ${chip(data.portfolio_fit_score)} | ${t("agentOutput.regime.confidence")} ${chip(data.regime_confidence)}`,
        fitNotes ? `${t("agentOutput.regime.fitNotes")} ${fitNotes}` : "",
        hist,
        md ? `${t("agentOutput.regime.mismatchDrivers")}\n${md}` : "",
        mm ? `${t("agentOutput.regime.mismatches")}\n${mm}` : "",
        data.summary ? `${t("agentOutput.regime.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "theme": {
      const data = Array.isArray(out.theme_results) ? out.theme_results[0] : out;
      const scored = (data.scored_themes || []).slice(0, 5).map(st => {
        const ev = (st.key_evidence && st.key_evidence[0]) ? String(st.key_evidence[0]).slice(0, 80) : "";
        return `  ${escapeHtml(st.theme)} · ${escapeHtml(t("agentOutput.theme.exposure"))} ${fmtPctFromRatio(st.portfolio_exposure, 0)} · ${escapeHtml(t("agentOutput.theme.newsStrength"))} ${fmtPctFromRatio(st.news_strength, 0)} · ${escapeHtml(t("agentOutput.theme.confidenceShort"))} ${fmtPctFromRatio(st.confidence, 0)}${ev ? " — " + escapeHtml(ev) : ""}`;
      }).join("\n");
      const dom = (data.synthesis && data.synthesis.dominant_themes || []).slice(0, 4).map(escapeHtml).join(" · ");
      const bet = (data.implicit_portfolio_bet || "").trim();
      const crowd = (data.crowding_risks || []).map(escapeHtml).join("; ");
      return [
        `${t("agentOutput.theme.alignment")} ${chip(data.alignment_score)}`,
        bet ? `${t("agentOutput.theme.implicitBet")} ${escapeHtml(bet.length > 200 ? bet.slice(0, 200) + "…" : bet)}` : "",
        dom ? `${t("agentOutput.theme.dominant")} ${dom}` : "",
        scored || "",
        crowd ? `${t("agentOutput.theme.crowding")} ${crowd}` : "",
        data.summary ? `${t("agentOutput.theme.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "validation": {
      const data = out.validation_review || out;
      const crit = (data.critical_issues || []).slice(0, 4)
        .map(i => `  [${escapeHtml(severityLabel((i.severity || "").toLowerCase()))}] ${escapeHtml(i.issue)}`)
        .join("\n");
      const br = (data.thesis_breaks || []).map(t => "  !! " + escapeHtml(t)).join("\n");
      return [
        `${t("agentOutput.validation.consistency")} ${chip(data.confidence_score)}`,
        crit ? crit : "",
        br ? `${t("agentOutput.validation.thesisBreaks")}\n${br}` : "",
        data.summary ? `${t("agentOutput.validation.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "planner": {
      const sections = [];
      const nf = out.news_focus;
      if (nf) {
        const lines = [];
        const pg = nf.portfolio_goal || "";
        if (pg) lines.push(`<b>${escapeHtml(t("agentOutput.planner.portfolioGoal"))}</b> ${escapeHtml(pg.length > 280 ? `${pg.slice(0, 280)}…` : pg)}`);
        const pq = nf.portfolio_search_queries || [];
        if (pq.length) {
          lines.push(`<b>${escapeHtml(t("agentOutput.planner.macroTopics"))}</b>`);
          for (const q of pq.slice(0, 3)) {
            lines.push(`  <span class="mono">•</span> ${escapeHtml(q.length > 200 ? `${q.slice(0, 200)}…` : q)}`);
          }
        }
        const goals = nf.position_goals || [];
        if (goals.length) {
          lines.push(`<b>${escapeHtml(t("agentOutput.planner.positionGoals"))}</b>`);
          for (const g of goals.slice(0, 12)) {
            const tickerText = escapeHtml(g.ticker || "");
            const gg = escapeHtml((g.goal || "").length > 160 ? `${(g.goal || "").slice(0, 160)}…` : (g.goal || ""));
            lines.push(`  <span class="mono">${tickerText}</span> — ${gg || "—"}`);
            const lq = (g.latest_news_query || "").trim();
            if (lq) {
              lines.push(
                `    <span class="muted-text">${escapeHtml(t("agentOutput.planner.latestNews"))}</span> ${escapeHtml(lq.length > 180 ? `${lq.slice(0, 180)}…` : lq)}`,
              );
            }
          }
          if (goals.length > 12) lines.push(`  <span class="muted-text">${escapeHtml(t("agentOutput.planner.more", { count: goals.length - 12 }))}</span>`);
        }
        const macros = (nf.macro_indicator_tickers || []).filter(Boolean);
        if (macros.length) {
          lines.push(
            `<b>${escapeHtml(t("agentOutput.planner.macroIndicators"))}</b> ${macros.map(escapeHtml).join(", ")}`,
          );
        }
        if (lines.length) sections.push(`<b>${escapeHtml(t("agentOutput.planner.phase1"))}</b>\n${lines.join("\n")}`);
      }
      const dc = out.downstream_context;
      if (dc && typeof dc === "object") {
        const rationale = (dc.brief_rationale || "").trim();
        const rf = (dc.risk_focus || "").trim();
        const regf = (dc.regime_focus || "").trim();
        const tf = (dc.theme_focus || "").trim();
        const blocks = [];
        if (rationale) blocks.push(`<b>${escapeHtml(t("agentOutput.planner.rationale"))}</b> ${escapeHtml(rationale.length > 400 ? `${rationale.slice(0, 400)}…` : rationale)}`);
        if (rf) blocks.push(`<b>${escapeHtml(t("agentOutput.planner.riskFocus"))}</b><br>${escapeHtml(rf.length > 1200 ? `${rf.slice(0, 1200)}…` : rf).replace(/\n/g, "<br>")}`);
        if (regf) blocks.push(`<b>${escapeHtml(t("agentOutput.planner.regimeFocus"))}</b><br>${escapeHtml(regf.length > 1200 ? `${regf.slice(0, 1200)}…` : regf).replace(/\n/g, "<br>")}`);
        if (tf) blocks.push(`<b>${escapeHtml(t("agentOutput.planner.themeFocus"))}</b><br>${escapeHtml(tf.length > 1200 ? `${tf.slice(0, 1200)}…` : tf).replace(/\n/g, "<br>")}`);
        if (blocks.length) sections.push(`<b>${escapeHtml(t("agentOutput.planner.phase2"))}</b><br><br>${blocks.join("<br><br>")}`);
      }
      return sections.length ? sections.join("<br><br>") : `<em>${escapeHtml(t("agentOutput.planner.noOutputYet"))}</em>`;
    }
    case "manager": {
      const data = out.manager_review || out.planner_review || out;
      const acts = (data.actions || []).slice(0, 5)
        .map(a =>
          `  [${escapeHtml(priorityLabel(a.priority))}] ${escapeHtml(actionTypeLabel(a.action_type))} ${escapeHtml(actionScopeLabel(normalizeActionScope(a)))} · ${escapeHtml(a.position)}`
        )
        .join("\n");
      const es = data.executive_summary ? escapeHtml(data.executive_summary.slice(0, 200)) : "";
      return [
        `${t("agentOutput.manager.confidence")} ${chip(data.overall_confidence)}`,
        acts || "",
        es ? `${t("agentOutput.manager.summary")} ${es}${(data.executive_summary || "").length > 200 ? "…" : ""}` : "",
      ].filter(Boolean).join("\n\n");
    }
    default:
      return `<pre>${escapeHtml(JSON.stringify(out, null, 2).slice(0, 400))}</pre>`;
  }
}

function formatSavedAt(iso) {
  return formatDateTime(iso);
}

function formatSavedReviewMeta(savedAt, reviewId, contentLocale) {
  const when = savedAt ? formatSavedAt(savedAt) : "";
  const idShort = reviewId ? String(reviewId).slice(0, 8) : "";
  const parts = [when];
  if (idShort) parts.push(t("history.reviewId", { id: `${idShort}…` }));
  if (contentLocale) parts.push(t("history.localeBadge", { locale: getLocaleLabel(contentLocale) }));
  return parts.filter(Boolean).join(" · ");
}

function isManagerReviewLike(value) {
  if (!value || typeof value !== "object") return false;
  return MANAGER_REVIEW_FIELDS.some((field) =>
    Object.prototype.hasOwnProperty.call(value, field)
  );
}

function managerFromReviewBundle(bundle) {
  if (!bundle || typeof bundle !== "object") return null;
  return bundle.manager || bundle.planner || (isManagerReviewLike(bundle) ? bundle : null);
}

function normalizeReviewBundle(bundle) {
  if (!bundle || typeof bundle !== "object") return bundle;
  if (bundle.manager || bundle.planner) {
    return {
      ...bundle,
      requestedLocale: bundle.requestedLocale || bundle.contentLocale || "en",
      contentLocale: bundle.contentLocale || bundle.requestedLocale || "en",
      translationFallbackUsed: Boolean(bundle.translationFallbackUsed),
      userRefinements: normalizeUserRefinements(bundle.userRefinements),
    };
  }
  if (!isManagerReviewLike(bundle)) return bundle;
  return {
    manager: bundle,
    requestedLocale: bundle.requestedLocale || bundle.contentLocale || "en",
    contentLocale: bundle.contentLocale || bundle.requestedLocale || "en",
    translationFallbackUsed: Boolean(bundle.translationFallbackUsed),
    savedAt: bundle.savedAt,
    reviewId: bundle.reviewId,
    portfolioName: bundle.portfolioName || "",
    validation: bundle.validation ?? null,
    agentOutputs: bundle?.agentOutputs && typeof bundle.agentOutputs === "object" ? bundle.agentOutputs : {},
    agentOutputUpdatedAt:
      bundle?.agentOutputUpdatedAt && typeof bundle.agentOutputUpdatedAt === "object"
        ? bundle.agentOutputUpdatedAt
        : {},
    stepLogs: bundle?.stepLogs && typeof bundle.stepLogs === "object" ? bundle.stepLogs : {},
    userRefinements: normalizeUserRefinements(bundle.userRefinements),
  };
}

function truncateDeepStrings(value, maxChars = MAX_PERSISTED_STRING_CHARS) {
  if (typeof value === "string") return truncateText(value, maxChars);
  if (Array.isArray(value)) return value.map((item) => truncateDeepStrings(item, maxChars));
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = truncateDeepStrings(v, maxChars);
    return out;
  }
  return value;
}

function compactAgentOutputsForStorage(outputs) {
  if (!outputs || typeof outputs !== "object") return {};
  const out = {};
  for (const [agent, payload] of Object.entries(outputs)) {
    out[agent] = truncateDeepStrings(payload, MAX_PERSISTED_STRING_CHARS);
  }
  return out;
}

function compactStepLogsForStorage(stepLogs) {
  if (!stepLogs || typeof stepLogs !== "object") return {};
  const out = {};
  for (const [agent, logs] of Object.entries(stepLogs)) {
    if (!Array.isArray(logs)) continue;
    out[agent] = logs
      .slice(-MAX_PERSISTED_STEP_LOGS)
      .map((entry) => ({
        at: String(entry?.at || ""),
        stepIndex: Number(entry?.stepIndex ?? -1),
        label: truncateText(String(entry?.label || ""), 240),
      }));
  }
  return out;
}

function restoreAnalysisTraceFromBundle(bundle) {
  if (!bundle || typeof bundle !== "object") return;
  for (const k of Object.keys(_agentOutputs)) delete _agentOutputs[k];
  for (const k of Object.keys(currentAgentOutputUpdatedAt)) delete currentAgentOutputUpdatedAt[k];
  for (const k of Object.keys(agentStepHistory)) delete agentStepHistory[k];
  if (bundle.agentOutputs && typeof bundle.agentOutputs === "object") {
    Object.assign(_agentOutputs, bundle.agentOutputs);
  }
  if (bundle.agentOutputUpdatedAt && typeof bundle.agentOutputUpdatedAt === "object") {
    Object.assign(currentAgentOutputUpdatedAt, bundle.agentOutputUpdatedAt);
  }
  if (bundle.stepLogs && typeof bundle.stepLogs === "object") {
    for (const [agent, logs] of Object.entries(bundle.stepLogs)) {
      if (!Array.isArray(logs)) continue;
      agentStepHistory[agent] = logs.slice(-MAX_STEP_HISTORY).map((entry) => ({
        at: String(entry?.at || ""),
        stepIndex: Number(entry?.stepIndex ?? -1),
        label: String(entry?.label || ""),
      }));
    }
  }
}

function migrateLegacyReviewToHistory() {
  try {
    if (localStorage.getItem(REVIEW_HISTORY_STORAGE_KEY)) return;
    const raw = localStorage.getItem(LAST_REVIEW_STORAGE_KEY);
    if (!raw) return;
    const bundle = normalizeReviewBundle(JSON.parse(raw));
    if (!managerFromReviewBundle(bundle)) return;
    localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify([bundle]));
  } catch {
    /* ignore */
  }
}

function loadReviewHistory() {
  try {
    migrateLegacyReviewToHistory();
    const raw = localStorage.getItem(REVIEW_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.map(normalizeReviewBundle);
  } catch {
    return [];
  }
}

function persistReviewBundle(bundle) {
  let list = loadReviewHistory().filter((b) => b?.reviewId !== bundle.reviewId);
  list.unshift(bundle);
  list = list.slice(0, MAX_REVIEW_HISTORY);
  try {
    localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify(list));
    localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(bundle));
  } catch {
    const fallbackBundle = { ...bundle };
    delete fallbackBundle.stepLogs;
    try {
      const fallbackList = [fallbackBundle, ...list.filter((b) => b?.reviewId !== bundle.reviewId)];
      localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify(fallbackList.slice(0, MAX_REVIEW_HISTORY)));
      localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(fallbackBundle));
      return;
    } catch {
      /* continue to aggressive trimming */
    }
    for (let n = list.length - 1; n >= 0; n--) {
      const trimmed = list.slice(0, n);
      try {
        if (trimmed.length) {
          localStorage.setItem(REVIEW_HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
          localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(trimmed[0]));
        } else {
          localStorage.removeItem(REVIEW_HISTORY_STORAGE_KEY);
          localStorage.setItem(LAST_REVIEW_STORAGE_KEY, JSON.stringify(bundle));
        }
        return;
      } catch {
        /* try smaller */
      }
    }
  }
}

function refreshSavedReviewSidebar(bundle) {
  const block = document.getElementById("saved-review-block");
  const meta = document.getElementById("saved-review-meta");
  if (!block || !meta) return;
  block.classList.remove("hidden");
  meta.textContent = formatSavedReviewMeta(bundle.savedAt, bundle.reviewId, bundle.contentLocale);
}

function initSavedReview() {
  try {
    migrateLegacyReviewToHistory();
    const list = loadReviewHistory();
    const bundle = list[0];
    if (!managerFromReviewBundle(bundle)) return;
    refreshSavedReviewSidebar(bundle);
  } catch {
    /* ignore */
  }
}

function riskReviewFromAgentOutputs(agentOutputs) {
  const risk = agentOutputs?.risk;
  if (!risk || typeof risk !== "object") return null;
  if (Array.isArray(risk.risk_results)) return risk.risk_results[0] || null;
  return risk.risk_review || risk;
}

function regimeReviewFromAgentOutputs(agentOutputs) {
  const regime = agentOutputs?.regime;
  if (!regime || typeof regime !== "object") return null;
  if (Array.isArray(regime.regime_results)) return regime.regime_results[0] || null;
  return regime.regime_review || regime;
}

function sortedMetricEntries(values, { absolute = false } = {}) {
  if (!values || typeof values !== "object") return [];
  return Object.entries(values)
    .map(([name, value]) => [name, toFiniteNumber(value)])
    .filter((entry) => entry[1] != null)
    .sort((a, b) => {
      const av = absolute ? Math.abs(a[1]) : a[1];
      const bv = absolute ? Math.abs(b[1]) : b[1];
      return bv - av;
    });
}

function defaultUserRefinements() {
  return {
    news: { sources: [] },
    regime: { periods: [] },
    theme: { themes: [] },
    risk: { scenarios: [] },
  };
}

function cleanRefinementText(value, maxChars = 500) {
  return truncateText(String(value || "").trim(), maxChars);
}

function normalizeStringArray(value, maxItems = 12) {
  if (typeof value === "string") {
    return value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, maxItems);
  }
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "").trim()).filter(Boolean).slice(0, maxItems);
}

function normalizeUserRefinements(value) {
  const base = defaultUserRefinements();
  const src = value && typeof value === "object" ? value : {};
  base.news.sources = Array.isArray(src.news?.sources)
    ? src.news.sources.map((item) => ({
        title: cleanRefinementText(item?.title, 160),
        url: cleanRefinementText(item?.url, 300),
        tag: cleanRefinementText(item?.tag, 80),
        note: cleanRefinementText(item?.note, 800),
      })).filter((item) => item.title || item.url || item.note)
    : [];
  base.regime.periods = Array.isArray(src.regime?.periods)
    ? src.regime.periods.map((item) => ({
        label: cleanRefinementText(item?.label, 120),
        start_date: cleanRefinementText(item?.start_date, 24),
        end_date: cleanRefinementText(item?.end_date, 24),
        note: cleanRefinementText(item?.note, 800),
      })).filter((item) => item.label || item.start_date || item.end_date || item.note)
    : [];
  base.theme.themes = Array.isArray(src.theme?.themes)
    ? src.theme.themes.map((item) => ({
        theme: cleanRefinementText(item?.theme, 120),
        description: cleanRefinementText(item?.description, 800),
        supporting_assets: normalizeStringArray(item?.supporting_assets),
        note: cleanRefinementText(item?.note, 800),
      })).filter((item) => item.theme || item.description || item.note)
    : [];
  base.risk.scenarios = Array.isArray(src.risk?.scenarios)
    ? src.risk.scenarios.map((item) => ({
        name: cleanRefinementText(item?.name, 120),
        shock_description: cleanRefinementText(item?.shock_description, 800),
        affected_positions: normalizeStringArray(item?.affected_positions),
        expected_direction: cleanRefinementText(item?.expected_direction, 160),
      })).filter((item) => item.name || item.shock_description || item.expected_direction)
    : [];
  return base;
}

function ensureBundleRefinements(bundle) {
  if (!bundle || typeof bundle !== "object") return defaultUserRefinements();
  bundle.userRefinements = normalizeUserRefinements(bundle.userRefinements);
  return bundle.userRefinements;
}

function currentUserRefinements() {
  const bundle = currentResultsView?.bundle;
  if (bundle) return ensureBundleRefinements(bundle);
  return normalizeUserRefinements(currentResultsView?.userRefinements);
}

function persistCurrentRefinements() {
  const bundle = currentResultsView?.bundle;
  if (!bundle || !managerFromReviewBundle(bundle)) return;
  ensureBundleRefinements(bundle);
  persistReviewBundle(bundle);
  refreshSavedReviewSidebar(bundle);
}

function refinementListFor(agent) {
  const refs = currentUserRefinements();
  if (agent === "news") return refs.news.sources;
  if (agent === "regime") return refs.regime.periods;
  if (agent === "theme") return refs.theme.themes;
  if (agent === "risk") return refs.risk.scenarios;
  return [];
}

function addRefinement(agent, item) {
  const bundle = currentResultsView?.bundle;
  if (!bundle) return;
  const refs = ensureBundleRefinements(bundle);
  if (agent === "news") refs.news.sources.push(item);
  if (agent === "regime") refs.regime.periods.push(item);
  if (agent === "theme") refs.theme.themes.push(item);
  if (agent === "risk") refs.risk.scenarios.push(item);
  persistCurrentRefinements();
  renderAgentAnalysisTabs(currentResultsView);
}

function deleteRefinement(agent, index) {
  const bundle = currentResultsView?.bundle;
  if (!bundle) return;
  const list = refinementListFor(agent);
  if (index < 0 || index >= list.length) return;
  list.splice(index, 1);
  persistCurrentRefinements();
  renderAgentAnalysisTabs(currentResultsView);
}

function emptyAnalysisHtml() {
  return `<p class="evidence-empty">${escapeHtml(t("agentAnalysis.empty"))}</p>`;
}

function listHtml(items) {
  const clean = (Array.isArray(items) ? items : []).map((item) => String(item || "").trim()).filter(Boolean);
  if (!clean.length) return emptyAnalysisHtml();
  return `<ul class="analysis-list">${clean.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function pillRowHtml(items) {
  const clean = (Array.isArray(items) ? items : []).map((item) => String(item || "").trim()).filter(Boolean);
  if (!clean.length) return emptyAnalysisHtml();
  return `<div class="analysis-chip-row">${clean.map((item) => `<span class="analysis-pill">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function kvHtml(rows) {
  const clean = rows.filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "");
  if (!clean.length) return emptyAnalysisHtml();
  return `<dl class="analysis-kv">${clean.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}</dl>`;
}

function metricListHtml(values, { percent = false, signed = false } = {}) {
  const rows = sortedMetricEntries(values, { absolute: signed }).slice(0, 10);
  if (!rows.length) return emptyAnalysisHtml();
  return rows.map(([name, value]) => `
    <div class="analysis-item">
      <div class="analysis-item-title"><span>${escapeHtml(name)}</span><span class="analysis-item-meta">${escapeHtml(percent ? fmtPctFromRatio(value, 1) : fmtNum(value, 2, signed))}</span></div>
    </div>
  `).join("");
}

function parseNewsResearchRuns(raw) {
  const text = String(raw || "").trim();
  if (!text) return [];
  return text.split(/\n\n---\n\n/g).map((block) => {
    const match = block.match(/^### Query:\s*(.+)\n([\s\S]*)$/);
    return match
      ? { query: match[1].trim(), body: match[2].trim() }
      : { query: t("agentAnalysis.news.unknownQuery"), body: block.trim() };
  }).filter((item) => item.body || item.query);
}

function refinementFormHtml(agent) {
  if (!currentResultsView?.bundle) return "";
  if (agent === "news") {
    return `
      <form class="analysis-form" data-refinement-form="news">
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.news.sourceTitle"))}<input name="title" required /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.news.sourceUrl"))}<input name="url" type="url" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.news.sourceTag"))}<input name="tag" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.news.sourceNote"))}<textarea name="note"></textarea></label></div>
        <button type="submit" class="btn-secondary">${escapeHtml(t("agentAnalysis.news.addSource"))}</button>
      </form>
    `;
  }
  if (agent === "regime") {
    return `
      <form class="analysis-form" data-refinement-form="regime">
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.regime.periodLabel"))}<input name="label" required /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.regime.startDate"))}<input name="start_date" type="date" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.regime.endDate"))}<input name="end_date" type="date" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.regime.periodNote"))}<textarea name="note"></textarea></label></div>
        <button type="submit" class="btn-secondary">${escapeHtml(t("agentAnalysis.regime.addPeriod"))}</button>
      </form>
    `;
  }
  if (agent === "theme") {
    return `
      <form class="analysis-form" data-refinement-form="theme">
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.theme.themeName"))}<input name="theme" required /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.theme.supportingAssets"))}<input name="supporting_assets" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.theme.description"))}<textarea name="description"></textarea></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.theme.note"))}<textarea name="note"></textarea></label></div>
        <button type="submit" class="btn-secondary">${escapeHtml(t("agentAnalysis.theme.addTheme"))}</button>
      </form>
    `;
  }
  if (agent === "risk") {
    return `
      <form class="analysis-form" data-refinement-form="risk">
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.risk.scenarioName"))}<input name="name" required /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.risk.affectedPositions"))}<input name="affected_positions" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.risk.expectedDirection"))}<input name="expected_direction" /></label></div>
        <div class="analysis-field"><label>${escapeHtml(t("agentAnalysis.risk.shockDescription"))}<textarea name="shock_description" required></textarea></label></div>
        <button type="submit" class="btn-secondary">${escapeHtml(t("agentAnalysis.risk.addScenario"))}</button>
      </form>
    `;
  }
  return "";
}

function renderRefinementList(agent) {
  const list = refinementListFor(agent);
  if (!list.length) return `<div class="analysis-refinement-list">${emptyAnalysisHtml()}</div>`;
  return `<div class="analysis-refinement-list">${list.map((item, index) => {
    let title = "";
    let meta = "";
    let note = "";
    if (agent === "news") {
      title = item.title || item.url || t("agentAnalysis.news.sourceFallback");
      meta = [item.tag, item.url].filter(Boolean).join(" · ");
      note = item.note;
    } else if (agent === "regime") {
      title = item.label || t("agentAnalysis.regime.periodFallback");
      meta = [item.start_date, item.end_date].filter(Boolean).join(" to ");
      note = item.note;
    } else if (agent === "theme") {
      title = item.theme || t("agentAnalysis.theme.themeFallback");
      meta = (item.supporting_assets || []).join(", ");
      note = item.description || item.note;
    } else if (agent === "risk") {
      title = item.name || t("agentAnalysis.risk.scenarioFallback");
      meta = (item.affected_positions || []).join(", ");
      note = item.shock_description || item.expected_direction;
    }
    return `
      <div class="analysis-refinement-row">
        <div>
          <strong>${escapeHtml(title)}</strong>
          ${meta ? `<p>${escapeHtml(meta)}</p>` : ""}
          ${note ? `<p>${escapeHtml(note)}</p>` : ""}
        </div>
        <button type="button" class="analysis-delete-btn" data-delete-refinement="${agent}" data-refinement-index="${index}" aria-label="${escapeHtml(t("agentAnalysis.delete"))}">×</button>
      </div>
    `;
  }).join("")}</div>`;
}

function refinementPanelHtml(agent, titleKey) {
  return `
    <div class="analysis-refinement">
      <div class="analysis-section">
        <h4>${escapeHtml(t(titleKey))}</h4>
        ${refinementFormHtml(agent)}
        ${renderRefinementList(agent)}
      </div>
    </div>
  `;
}

function renderNewsAnalysisTab(view) {
  const out = view?.agentOutputs?.news || {};
  const review = out.news_review || {};
  const queries = parseNewsResearchRuns(out.news_research_text);
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.news.briefing"))}</h4>${kvHtml([
          [t("agentOutput.news.macro"), review.macro_context],
          [t("agentOutput.news.summary"), review.summary],
          [t("agentAnalysis.news.queryCount"), out.news_research_query_count],
        ])}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.news.themes"))}</h4>${pillRowHtml(review.market_themes)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.news.keyEvents"))}</h4>${listHtml(review.key_events)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.news.thesisRisks"))}</h4>${listHtml(review.thesis_risks)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.news.consideredResearch"))}</h4>${queries.length ? queries.map((item) => `
          <div class="analysis-item">
            <div class="analysis-item-title"><span>${escapeHtml(item.query)}</span></div>
            <pre class="analysis-raw-block">${escapeHtml(truncateText(item.body, 1600))}</pre>
          </div>
        `).join("") : emptyAnalysisHtml()}</div>
      </div>
      ${refinementPanelHtml("news", "agentAnalysis.news.userSources")}
    </div>
  `;
}

function renderRiskAnalysisTab(view) {
  const risk = riskReviewFromAgentOutputs(view?.agentOutputs);
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.risk.overview"))}</h4>${risk ? kvHtml([
          [t("agentOutput.risk.riskScore"), `${risk.risk_score ?? "—"}/10`],
          [t("agentOutput.risk.worstScenario"), risk.worst_scenario ? `${risk.worst_scenario.name || ""} ${fmtNum(risk.worst_scenario.estimated_portfolio_loss_pct, 1, true)}%` : ""],
          [t("agentOutput.risk.summary"), risk.summary],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.factorLoadings"))}</h4>${metricListHtml(risk?.factor_loadings, { signed: true })}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.riskContribution"))}</h4>${metricListHtml(risk?.factor_risk_contribution, { percent: true })}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.marginalRiskTicker"))}</h4>${metricListHtml(risk?.marginal_risk_by_ticker, { percent: true })}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.scenarios"))}</h4>${risk?.scenario_losses?.length ? risk.scenario_losses.map((item) => `
          <div class="analysis-item"><div class="analysis-item-title"><span>${escapeHtml(item.scenario || t("agentOutput.risk.scenarioFallback"))}</span><span class="analysis-item-meta">${escapeHtml(fmtNum(item.estimated_portfolio_loss_pct, 1, true))}%</span></div>${pillRowHtml(item.most_affected_positions)}</div>
        `).join("") : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.topRisks"))}</h4>${listHtml([].concat(risk?.top_risks || [], risk?.concentration_issues || [], risk?.hidden_concentration || [], risk?.fragilities || []))}</div>
      </div>
      ${refinementPanelHtml("risk", "agentAnalysis.risk.userScenarios")}
    </div>
  `;
}

function renderRegimeAnalysisTab(view) {
  const regime = regimeReviewFromAgentOutputs(view?.agentOutputs);
  const hist = regime?.historical_outcome || {};
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.regime.overview"))}</h4>${regime ? kvHtml([
          [t("agentOutput.regime.regime"), regime.current_regime],
          [t("agentOutput.regime.fit"), `${regime.portfolio_fit_score ?? "—"}/10`],
          [t("agentOutput.regime.confidence"), `${regime.regime_confidence ?? "—"}/10`],
          [t("agentOutput.regime.summary"), regime.summary],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.regime.state"))}</h4>${regime?.state_vector ? kvHtml([
          [t("agentOutput.regime.stateVector.inflation"), stateValueLabel(regime.state_vector.inflation_trend)],
          [t("agentOutput.regime.stateVector.rates"), stateValueLabel(regime.state_vector.rates_trend)],
          [t("agentOutput.regime.stateVector.growth"), stateValueLabel(regime.state_vector.growth_trend)],
          [t("agentOutput.regime.stateVector.liquidity"), stateValueLabel(regime.state_vector.liquidity)],
          [t("agentOutput.regime.stateVector.volatility"), stateValueLabel(regime.state_vector.volatility)],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("results.historicalRegimeAnalogs"))}</h4>${kvHtml([
          [t("results.analogPeriods"), hist.analog_periods_identified ?? ""],
          [t("results.analogAvgReturn"), hist.avg_return == null ? "" : fmtPctFromRatio(hist.avg_return, 1)],
          [t("results.analogMaxDrawdown"), hist.max_drawdown == null ? "" : fmtPctAbsFromRatio(hist.max_drawdown, 1)],
          [t("results.analogWinRate"), hist.win_rate == null ? "" : fmtPctAbsFromRatio(hist.win_rate, 0)],
          [t("agentAnalysis.regime.message"), hist.message],
        ])}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.regime.mismatchDrivers"))}</h4>${listHtml([].concat(regime?.mismatch_drivers || [], regime?.mismatches || [], regime?.fit_notes || []))}</div>
      </div>
      ${refinementPanelHtml("regime", "agentAnalysis.regime.userPeriods")}
    </div>
  `;
}

function renderThemeAnalysisTab(view) {
  const theme = agentReviewFromView(view || {}, "theme", "theme_results");
  const synthesis = theme?.synthesis || {};
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.overview"))}</h4>${theme ? kvHtml([
          [t("agentOutput.theme.alignment"), `${theme.alignment_score ?? "—"}/10`],
          [t("agentOutput.theme.implicitBet"), theme.implicit_portfolio_bet],
          [t("agentOutput.theme.summary"), theme.summary],
          [t("agentAnalysis.theme.drift"), synthesis.theme_drift_note],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.theme.dominant"))}</h4>${pillRowHtml(synthesis.dominant_themes)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.scoredThemes"))}</h4>${theme?.scored_themes?.length ? theme.scored_themes.map((item) => `
          <div class="analysis-item">
            <div class="analysis-item-title"><span>${escapeHtml(item.theme)}</span><span class="analysis-item-meta">${escapeHtml(fmtPctFromRatio(item.portfolio_exposure, 0))} / ${escapeHtml(fmtPctFromRatio(item.news_strength, 0))} / ${escapeHtml(fmtPctFromRatio(item.confidence, 0))}</span></div>
            ${pillRowHtml(item.supporting_assets)}
            ${listHtml(item.key_evidence)}
          </div>
        `).join("") : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.positionProfiles"))}</h4>${theme?.position_profiles?.length ? theme.position_profiles.map((item) => `
          <div class="analysis-item"><div class="analysis-item-title"><span>${escapeHtml(item.ticker)}</span><span class="analysis-item-meta">${escapeHtml(item.sector || "")}</span></div>${pillRowHtml(item.candidate_themes)}${item.revenue_drivers ? `<p class="muted-text">${escapeHtml(item.revenue_drivers)}</p>` : ""}</div>
        `).join("") : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.risks"))}</h4>${listHtml([].concat(theme?.crowding_risks || [], theme?.momentum_conflicts || [], synthesis.redundant_expressions || [], synthesis.missing_exposures || []))}</div>
      </div>
      ${refinementPanelHtml("theme", "agentAnalysis.theme.userThemes")}
    </div>
  `;
}

function renderValidationAnalysisTab(view) {
  const validation = view?.validation || {};
  return `
    <div class="analysis-section"><h4>${escapeHtml(t("agents.validation.label"))}</h4>${kvHtml([
      [t("agentOutput.validation.consistency"), validation.confidence_score == null ? "" : `${validation.confidence_score}/10`],
      [t("agentOutput.validation.summary"), validation.summary],
    ])}</div>
    <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.validation.thesisBreaks"))}</h4>${listHtml([].concat((validation.critical_issues || []).map((item) => item?.issue || ""), validation.thesis_breaks || [], validation.internal_contradictions || []))}</div>
  `;
}

function renderManagerAnalysisTab(view) {
  const manager = view?.manager || {};
  return `
    <div class="analysis-section"><h4>${escapeHtml(t("agents.manager.label"))}</h4>${kvHtml([
      [t("agentOutput.manager.confidence"), manager.overall_confidence == null ? "" : `${manager.overall_confidence}/10`],
      [t("agentOutput.manager.summary"), manager.executive_summary],
      [t("results.doNothingCase"), manager.do_nothing_case],
    ])}</div>
    <div class="analysis-section"><h4>${escapeHtml(t("results.actionPlan"))}</h4>${sortedManagerActions(manager).length ? sortedManagerActions(manager).map((action) => `
      <div class="analysis-item"><div class="analysis-item-title"><span>${escapeHtml(formatActionTitle(action))}</span><span class="analysis-item-meta">${escapeHtml(priorityLabel(action.priority))}</span></div><p>${escapeHtml(action.rationale || action.risk_addressed || "")}</p></div>
    `).join("") : emptyAnalysisHtml()}</div>
  `;
}

function renderAgentAnalysisTabs(view = currentResultsView) {
  if (!view) return;
  if (view.bundle) ensureBundleRefinements(view.bundle);
  const renderers = {
    news: renderNewsAnalysisTab,
    risk: renderRiskAnalysisTab,
    regime: renderRegimeAnalysisTab,
    theme: renderThemeAnalysisTab,
    validation: renderValidationAnalysisTab,
    manager: renderManagerAnalysisTab,
  };
  Object.entries(renderers).forEach(([agent, renderer]) => {
    const panel = document.getElementById(`agent-panel-${agent}`);
    if (panel) panel.innerHTML = renderer(view);
  });
  switchAgentAnalysisTab(activeAgentAnalysisTab, { render: false });
}

function switchAgentAnalysisTab(agent, { render = true } = {}) {
  activeAgentAnalysisTab = ["news", "risk", "regime", "theme", "validation", "manager"].includes(agent) ? agent : "news";
  document.querySelectorAll(".agent-analysis-tab").forEach((tab) => {
    const active = tab.dataset.agentTab === activeAgentAnalysisTab;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.setAttribute("tabindex", active ? "0" : "-1");
  });
  document.querySelectorAll(".agent-analysis-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `agent-panel-${activeAgentAnalysisTab}`);
  });
  if (render) renderAgentAnalysisTabs(currentResultsView);
}

function wireAgentAnalysisControls() {
  document.querySelectorAll(".agent-analysis-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchAgentAnalysisTab(tab.dataset.agentTab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(document.querySelectorAll(".agent-analysis-tab"));
      const current = tabs.indexOf(tab);
      let next = current;
      if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      tabs[next]?.focus();
      switchAgentAnalysisTab(tabs[next]?.dataset.agentTab);
    });
  });
  document.getElementById("agent-analysis-panels")?.addEventListener("submit", (event) => {
    const form = event.target?.closest?.("[data-refinement-form]");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    const agent = form.dataset.refinementForm;
    if (agent === "news") {
      addRefinement("news", {
        title: cleanRefinementText(data.get("title"), 160),
        url: cleanRefinementText(data.get("url"), 300),
        tag: cleanRefinementText(data.get("tag"), 80),
        note: cleanRefinementText(data.get("note"), 800),
      });
    } else if (agent === "regime") {
      addRefinement("regime", {
        label: cleanRefinementText(data.get("label"), 120),
        start_date: cleanRefinementText(data.get("start_date"), 24),
        end_date: cleanRefinementText(data.get("end_date"), 24),
        note: cleanRefinementText(data.get("note"), 800),
      });
    } else if (agent === "theme") {
      addRefinement("theme", {
        theme: cleanRefinementText(data.get("theme"), 120),
        supporting_assets: normalizeStringArray(data.get("supporting_assets")),
        description: cleanRefinementText(data.get("description"), 800),
        note: cleanRefinementText(data.get("note"), 800),
      });
    } else if (agent === "risk") {
      addRefinement("risk", {
        name: cleanRefinementText(data.get("name"), 120),
        affected_positions: normalizeStringArray(data.get("affected_positions")),
        expected_direction: cleanRefinementText(data.get("expected_direction"), 160),
        shock_description: cleanRefinementText(data.get("shock_description"), 800),
      });
    }
  });
  document.getElementById("agent-analysis-panels")?.addEventListener("click", (event) => {
    const btn = event.target?.closest?.("[data-delete-refinement]");
    if (!btn) return;
    deleteRefinement(btn.dataset.deleteRefinement, Number(btn.dataset.refinementIndex));
  });
}

function applyResultsFromData(manager, validation, bundleOrAgentOutputs = null) {
  const bundle =
    bundleOrAgentOutputs && typeof bundleOrAgentOutputs === "object" && !Array.isArray(bundleOrAgentOutputs)
      ? ("manager" in bundleOrAgentOutputs || "portfolio" in bundleOrAgentOutputs || "reviewId" in bundleOrAgentOutputs
        ? bundleOrAgentOutputs
        : null)
      : null;
  const agentOutputs = bundle?.agentOutputs || (bundle ? _agentOutputs : (bundleOrAgentOutputs || _agentOutputs));
  currentResultsView = { manager, validation, bundle, agentOutputs };
  currentShareArtifact = null;
function riskReviewFromAgentOutputs(agentOutputs) {
  const risk = agentOutputs?.risk;
  if (!risk || typeof risk !== "object") return null;
  if (Array.isArray(risk.risk_results)) return risk.risk_results[0] || null;
  return risk.risk_review || risk;
}

function regimeReviewFromAgentOutputs(agentOutputs) {
  const regime = agentOutputs?.regime;
  if (!regime || typeof regime !== "object") return null;
  if (Array.isArray(regime.regime_results)) return regime.regime_results[0] || null;
  return regime.regime_review || regime;
}

function sortedMetricEntries(values, { absolute = false } = {}) {
  if (!values || typeof values !== "object") return [];
  return Object.entries(values)
    .map(([name, value]) => [name, toFiniteNumber(value)])
    .filter((entry) => entry[1] != null)
    .sort((a, b) => {
      const av = absolute ? Math.abs(a[1]) : a[1];
      const bv = absolute ? Math.abs(b[1]) : b[1];
      return bv - av;
    });
}

function renderEvidenceBars(containerId, entries, { signed = false, maxItems = 5 } = {}) {
  const el = document.getElementById(containerId);
  if (!el) return false;
  const rows = entries.slice(0, maxItems);
  if (!rows.length) {
    el.innerHTML = `<p class="evidence-empty">${escapeHtml(t("results.noComputedEvidence"))}</p>`;
    return false;
  }
  const maxAbs = Math.max(...rows.map(([, value]) => Math.abs(value)), 0.0001);
  el.innerHTML = rows.map(([name, value]) => {
    const width = Math.max(3, Math.min(100, Math.abs(value) / maxAbs * 100));
    const valueText = signed ? fmtNum(value, 2, true) : fmtPctFromRatio(value, 1);
    return `
      <div class="evidence-bar-row">
        <div class="evidence-bar-meta">
          <span>${escapeHtml(name)}</span>
          <strong>${escapeHtml(valueText)}</strong>
        </div>
        <div class="evidence-bar-track">
          <span class="evidence-bar-fill${value < 0 ? " negative" : ""}" style="width: ${width}%"></span>
        </div>
      </div>
    `;
  }).join("");
  return true;
}

function firstSentence(text, maxChars = 150) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const match = clean.match(/^(.+?[.!?])(?:\s|$)/);
  const sentence = (match ? match[1] : clean).trim();
  if (sentence.length <= maxChars) return sentence;
  return `${sentence.slice(0, maxChars - 1).trim()}…`;
}

function analogContextHtml(message) {
  const clean = String(message || "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const brief = firstSentence(clean);
  if (!brief || clean === brief) {
    return `<p class="analog-message muted-text">${escapeHtml(clean)}</p>`;
  }
  return `
    <div class="analog-message">
      <p class="muted-text">${escapeHtml(brief)}</p>
      <details class="analog-details">
        <summary>${escapeHtml(t("results.showAnalogDetails"))}</summary>
        <p>${escapeHtml(clean)}</p>
      </details>
    </div>
  `;
}

function renderAnalogStats(hist) {
  const statsEl = document.getElementById("regime-analog-stats");
  const msgEl = document.getElementById("regime-analog-message");
  if (!statsEl || !msgEl) return false;
  if (!hist || typeof hist !== "object") {
    statsEl.innerHTML = "";
    msgEl.innerHTML = `<p class="evidence-empty">${escapeHtml(t("results.noComputedEvidence"))}</p>`;
    return false;
  }
  const statRows = [
    [t("results.analogPeriods"), hist.analog_periods_identified ?? 0],
    [t("results.analogAvgReturn"), hist.avg_return == null ? "—" : fmtPctFromRatio(hist.avg_return, 1)],
    [t("results.analogMaxDrawdown"), hist.max_drawdown == null ? "—" : fmtPctAbsFromRatio(hist.max_drawdown, 1)],
    [t("results.analogWinRate"), hist.win_rate == null ? "—" : fmtPctAbsFromRatio(hist.win_rate, 0)],
  ];
  statsEl.innerHTML = statRows.map(([label, value]) => `
    <div class="analog-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>
  `).join("");
  msgEl.innerHTML = analogContextHtml(hist.message);
  return Boolean(hist.runner_available || hist.analog_periods_identified || hist.message);
}

function renderComputedEvidence(agentOutputs = _agentOutputs) {
  const section = document.getElementById("computed-evidence");
  if (!section) return;
  const risk = riskReviewFromAgentOutputs(agentOutputs);
  const regime = regimeReviewFromAgentOutputs(agentOutputs);
  const hasFactors = renderEvidenceBars(
    "factor-risk-chart",
    sortedMetricEntries(risk?.factor_risk_contribution),
  );
  const hasTickers = renderEvidenceBars(
    "ticker-risk-chart",
    sortedMetricEntries(risk?.marginal_risk_by_ticker),
  );
  const hasAnalogs = renderAnalogStats(regime?.historical_outcome);
  section.classList.toggle("hidden", !(hasFactors || hasTickers || hasAnalogs));
}

  const execEl = document.getElementById("exec-summary");
  execEl.textContent = manager?.executive_summary || "";

  const stance = manager?.portfolio_stance;
  const stanceEl = document.getElementById("portfolio-stance");
  if (stanceEl) {
    if (hasMeaningfulPortfolioStance(stance)) {
      stanceEl.classList.remove("hidden");
      const stanceValue = document.getElementById("stance-value");
      if (stanceValue) {
        const stanceName = normalizePortfolioStance(stance.stance);
        stanceValue.textContent = portfolioStanceLabel(stanceName);
        stanceValue.className = `table-chip stance-chip stance-${stanceName}`;
      }
      const stanceUrgency = document.getElementById("stance-urgency");
      if (stanceUrgency) {
        const urgency = normalizePriority(stance.urgency);
        stanceUrgency.textContent = priorityLabel(urgency);
        stanceUrgency.className = `table-chip priority-chip priority-${urgency}`;
      }
      setElementText("stance-primary-risk", stance.primary_risk);
      setElementText("stance-recommended-posture", stance.recommended_posture);
      setElementText("stance-rationale", stance.rationale);
    } else {
      stanceEl.classList.add("hidden");
      setElementText("stance-value", "");
      setElementText("stance-urgency", "");
      setElementText("stance-primary-risk", "");
      setElementText("stance-recommended-posture", "");
      setElementText("stance-rationale", "");
    }
  }

  const conf = toFiniteNumber(manager?.overall_confidence);
  const consistency = toFiniteNumber(validation?.confidence_score);
  document.getElementById("score-confidence").textContent =
    conf == null ? "—" : String(Math.round(conf));
  document.getElementById("score-consistency").textContent =
    consistency == null ? "—" : String(Math.round(consistency));

  const actions = sortedManagerActions(manager);
  setElementText(
    "overview-top-action",
    actions.length ? formatActionTitle(actions[0]) : t("share.noImmediateAction"),
  );
  renderComputedEvidence(agentOutputs);
  renderAgentAnalysisTabs(currentResultsView);
  renderActionsTable(actions);
  renderActionCards(actions);

  document.getElementById("do-nothing").textContent =
    manager?.do_nothing_case || "";
  renderShareArtifact();
}

function showResultsModal() {
  const el = document.getElementById("results-modal");
  if (!el) return;
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("results-modal-close")?.focus();
}

function hideResultsModal() {
  const el = document.getElementById("results-modal");
  if (!el) return;
  el.classList.add("hidden");
  const historyOpen = !document.getElementById("history-modal")?.classList.contains("hidden");
  const llmOpen = !document.getElementById("llm-config-modal")?.classList.contains("hidden");
  if (!historyOpen && !llmOpen) document.body.style.overflow = "";
}

function renderDrawerReasoning(agent) {
  const reasoningEl = document.getElementById("drawer-reasoning");
  if (!reasoningEl) return;
  const steps = agentStepHistory[agent] || [];
  if (!steps.length) {
    reasoningEl.innerHTML = "";
    return;
  }
  reasoningEl.innerHTML = `
    <div class="drawer-reasoning-heading">Reasoning Trace</div>
    <ul class="drawer-reasoning-list">
      ${steps.map((entry) => `<li>${escapeHtml(entry.at)} ${escapeHtml(entry.label)}</li>`).join("")}
    </ul>
  `;
}

function showLlmConfigModal() {
  const el = document.getElementById("llm-config-modal");
  if (!el) return;
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("llm-config-modal-close")?.focus();
}

function hideLlmConfigModal() {
  const el = document.getElementById("llm-config-modal");
  if (!el) return;
  el.classList.add("hidden");
  const historyOpen = !document.getElementById("history-modal")?.classList.contains("hidden");
  const resultsOpen = !document.getElementById("results-modal")?.classList.contains("hidden");
  if (!historyOpen && !resultsOpen) document.body.style.overflow = "";
}

function openSavedReviewFromStorage() {
  try {
    migrateLegacyReviewToHistory();
    const list = loadReviewHistory();
    const bundle = list[0];
    if (!bundle) {
      showToast(t("history.noSavedReviewYet"), true);
      return;
    }
    const mgr = managerFromReviewBundle(bundle);
    if (!mgr) {
      showToast(t("history.savedReviewMissing"), true);
      return;
    }
    restoreAnalysisTraceFromBundle(bundle);
    applyResultsFromData(mgr, bundle.validation, bundle.agentOutputs || _agentOutputs);
    currentResultsView = { ...(currentResultsView || {}), bundle };
    showResultsModal();
  } catch {
    showToast(t("history.savedReviewLoadError"), true);
  }
}

function historyRowLabel(bundle) {
  const name = (bundle.portfolioName || "").trim() || t("common.portfolio");
  const when = bundle.savedAt ? formatSavedAt(bundle.savedAt) : "";
  const idShort = bundle.reviewId ? String(bundle.reviewId).slice(0, 8) : "";
  const parts = [name];
  if (when) parts.push(when);
  if (idShort) parts.push(`${idShort}…`);
  if (bundle.contentLocale) parts.push(getLocaleLabel(bundle.contentLocale));
  return parts.join(" · ");
}

function renderHistoryList() {
  const ul = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  if (!ul) return;
  const list = loadReviewHistory();
  ul.innerHTML = "";
  if (list.length === 0) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  let added = 0;
  for (const bundle of list) {
    const mgr = managerFromReviewBundle(bundle);
    if (!mgr) continue;
    added += 1;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-row-btn";
    btn.setAttribute("aria-label", historyRowLabel(bundle));
    btn.innerHTML = `
      <span class="history-row-top">
        <span class="history-row-title">${escapeHtml((bundle.portfolioName || "").trim() || t("common.portfolio"))}</span>
        <span class="history-row-time">${escapeHtml(formatSavedReviewMeta(bundle.savedAt, bundle.reviewId, bundle.contentLocale))}</span>
      </span>
      <span class="history-row-preview">${escapeHtml(
        truncateText(mgr.executive_summary || mgr.do_nothing_case || t("history.previewFallback"), 160),
      )}</span>
    `;
    btn.addEventListener("click", () => {
      restoreAnalysisTraceFromBundle(bundle);
      applyResultsFromData(mgr, bundle.validation, bundle.agentOutputs || _agentOutputs);
      currentResultsView = { ...(currentResultsView || {}), bundle };
      hideHistoryModal();
      showResultsModal();
    });
    li.appendChild(btn);
    ul.appendChild(li);
  }
  if (added === 0 && empty) empty.classList.remove("hidden");
}

function showHistoryModal() {
  migrateLegacyReviewToHistory();
  renderHistoryList();
  const el = document.getElementById("history-modal");
  if (!el) return;
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("history-modal-close")?.focus();
}

function hideHistoryModal() {
  const el = document.getElementById("history-modal");
  if (!el) return;
  el.classList.add("hidden");
  if (!document.getElementById("results-modal")?.classList.contains("hidden")) {
    return;
  }
  if (!document.getElementById("llm-config-modal")?.classList.contains("hidden")) {
    return;
  }
  document.body.style.overflow = "";
}

async function renderResults(managerOutput, reviewId) {
  const res = await fetch(`/api/review/${reviewId}/result`);
  const {
    final_state,
    agent_outputs,
    agent_output_updated_at,
    requested_locale,
    content_locale,
    translation_fallback_used,
  } = await res.json();
  applySnapshotAgentOutputs(agent_outputs, agent_output_updated_at);

  const manager =
    managerOutput?.manager_review ||
    managerOutput?.planner_review ||
    final_state?.manager_review ||
    agent_outputs?.manager?.manager_review ||
    agent_outputs?.manager?.planner_review ||
    agent_outputs?.manager ||
    managerOutput;
  const validation = final_state?.validation_review;
  applyResultsFromData(manager, validation, agent_outputs || _agentOutputs);
  const bundle = {
    reviewId,
    savedAt: new Date().toISOString(),
    ...(lastStartBody?.portfolio
      ? { portfolio: lastStartBody.portfolio }
      : {
          portfolio: buildPortfolio(),
        }),
    portfolioName: document.getElementById("p-name")?.value?.trim() || "",
    requestedLocale: requested_locale || getLocale(),
    contentLocale: content_locale || requested_locale || getLocale(),
    translationFallbackUsed: Boolean(translation_fallback_used),
    manager,
    validation: validation ?? null,
    agentOutputs: compactAgentOutputsForStorage(_agentOutputs),
    agentOutputUpdatedAt: Object.assign({}, currentAgentOutputUpdatedAt),
    stepLogs: compactStepLogsForStorage(agentStepHistory),
    userRefinements: normalizeUserRefinements(currentResultsView?.bundle?.userRefinements),
  };
  applyResultsFromData(manager, validation, bundle);
  persistReviewBundle(bundle);
  refreshSavedReviewSidebar(bundle);
  showResultsModal();
}

async function renderFinalResultOnce(finalResult, attempt = 0) {
  const reviewId = finalResult?.reviewId;
  if (!reviewId) return;
  if (finalResultReviewId === reviewId || finalResultRenderInFlightId === reviewId) return;
  finalResultRenderInFlightId = reviewId;
  pendingFinalResult = null;
  try {
    await renderResults(finalResult.output, reviewId);
    finalResultReviewId = reviewId;
  } catch (err) {
    console.error("[final review render error]", err);
    if (currentReviewId === reviewId) {
      pendingFinalResult = finalResult;
      if (attempt < 3) {
        setTimeout(() => {
          void renderFinalResultOnce(finalResult, attempt + 1);
        }, 700 * (attempt + 1));
      } else {
        showToast(t("review.invalidResponseToast"), true);
      }
    }
  } finally {
    if (finalResultRenderInFlightId === reviewId) finalResultRenderInFlightId = null;
  }
}

// ── Elapsed timers ────────────────────────────────────────────────────────
function startElapsedTimer(agent) {
  agentStartTimes[agent] = Date.now();
  const el = document.querySelector(`#card-${agent} .agent-elapsed`);
  if (!el) return;
  agentTimerIds[agent] = setInterval(() => {
    el.textContent = fmtDuration(Math.floor((Date.now() - agentStartTimes[agent]) / 1000));
    refreshDrawer(agent);
  }, 1000);
}

function stopElapsedTimer(agent) {
  clearInterval(agentTimerIds[agent]);
  delete agentTimerIds[agent];
  agentEndTimes[agent] = Date.now();
  const el = document.querySelector(`#card-${agent} .agent-elapsed`);
  if (el) el.textContent = "";
}

// ── Stream log ────────────────────────────────────────────────────────────
function appendStreamEntry(agent, label, isActive) {
  const log = document.querySelector(`#card-${agent} .agent-stream-log`);
  const row = document.querySelector(`#card-${agent} .agent-stream-row`);
  if (!log || !row) return;
  row.classList.remove("hidden");
  log.querySelectorAll(".stream-entry.active").forEach(el => el.classList.remove("active"));
  const entry = document.createElement("div");
  entry.className = "stream-entry" + (isActive ? " active" : "");
  entry.textContent = label;
  log.appendChild(entry);
  while (log.children.length > 4) log.removeChild(log.firstChild);
}

function clearStreamLog(agent) {
  const log = document.querySelector(`#card-${agent} .agent-stream-log`);
  const row = document.querySelector(`#card-${agent} .agent-stream-row`);
  if (log) log.innerHTML = "";
  if (row) row.classList.add("hidden");
}

// ── Step tracking ─────────────────────────────────────────────────────────
function recordStep(agent, stepIndex, label) {
  if (!agentStepProgress[agent]) agentStepProgress[agent] = { active: -1, done: new Set(), labels: {} };
  const prev = agentStepProgress[agent].active;
  if (prev >= 0 && prev !== stepIndex) agentStepProgress[agent].done.add(prev);
  agentStepProgress[agent].active = stepIndex;
  agentStepProgress[agent].labels[stepIndex] = label;
  if (!agentStepHistory[agent]) agentStepHistory[agent] = [];
  agentStepHistory[agent].push({
    at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    stepIndex,
    label: String(label || ""),
  });
  if (agentStepHistory[agent].length > MAX_STEP_HISTORY) {
    agentStepHistory[agent] = agentStepHistory[agent].slice(-MAX_STEP_HISTORY);
  }
  appendStreamEntry(agent, label, true);
}

function completeAllSteps(agent) {
  const state = agentStepProgress[agent];
  if (!state) return;
  const plan = getAgentPlan(agent);
  if (plan) {
    for (let i = 0; i < plan.steps.length; i++) state.done.add(i);
  }
  state.active = -1;
}

// ── Agent drawer ─────────────────────────────────────────────────────────
function openDrawer(agent) {
  if (currentReviewId) void syncReviewSnapshot(currentReviewId, { silent: true });
  _drawerAgent = agent;
  _drawerOpen = true;
  renderDrawer(agent);
  const backdrop = document.getElementById("agent-drawer-backdrop");
  const drawer = document.getElementById("agent-drawer");
  backdrop.classList.remove("hidden");
  requestAnimationFrame(() => backdrop.classList.add("visible"));
  drawer.classList.remove("hidden");
  document.getElementById("drawer-close-btn")?.focus();
}

function closeDrawer() {
  _drawerOpen = false;
  _drawerAgent = null;
  if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  const backdrop = document.getElementById("agent-drawer-backdrop");
  const drawer = document.getElementById("agent-drawer");
  backdrop.classList.remove("visible");
  drawer.classList.add("hidden");
  setTimeout(() => {
    backdrop.classList.add("hidden");
  }, 200);
}

function togglePin() {
  _drawerPinned = !_drawerPinned;
  const btn = document.getElementById("drawer-pin-btn");
  const bar = document.getElementById("drawer-follow-bar");
  if (_drawerPinned) {
    btn.classList.add("pinned");
    btn.setAttribute("aria-label", t("drawer.unpin"));
    btn.title = t("drawer.unpin");
    const plan = getAgentPlan(_drawerAgent);
    bar.textContent = t("drawer.pinnedTo", { agent: plan?.label || _drawerAgent });
    bar.classList.add("pinned-bar");
    if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  } else {
    btn.classList.remove("pinned");
    btn.setAttribute("aria-label", t("drawer.pin"));
    btn.title = t("drawer.pin");
    bar.textContent = t("drawer.autoFollowing");
    bar.classList.remove("pinned-bar");
  }
}

function drawerAutoFollow(agent) {
  if (!_drawerOpen || _drawerPinned) return;
  if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  switchDrawerTo(agent);
}

function drawerAutoFollowDelayed(agent) {
  if (!_drawerOpen || _drawerPinned) return;
  if (_autoFollowTimer) clearTimeout(_autoFollowTimer);
  _autoFollowTimer = setTimeout(() => {
    _autoFollowTimer = null;
    if (_currentActiveAgent && _currentActiveAgent !== _drawerAgent) {
      switchDrawerTo(_currentActiveAgent);
    }
  }, AUTO_FOLLOW_DELAY_MS);
}

function switchDrawerTo(agent) {
  if (_drawerAgent === agent) { renderDrawer(agent); return; }
  const body = document.querySelector(".drawer-body");
  body.classList.add("switching");
  setTimeout(() => {
    _drawerAgent = agent;
    renderDrawer(agent);
    body.classList.remove("switching");
    body.classList.add("switching-in");
    setTimeout(() => body.classList.remove("switching-in"), 150);
  }, 80);
}

function refreshDrawer(agent) {
  if (_drawerOpen && _drawerAgent === agent) renderDrawer(agent);
}

function renderDrawer(agent) {
  const plan = getAgentPlan(agent);
  if (!plan) return;
  const state = agentStepProgress[agent] || { active: -1, done: new Set(), labels: {} };

  document.getElementById("drawer-agent-icon").innerHTML = AGENT_SVG[agent] || "";
  document.getElementById("drawer-agent-name").textContent = plan.label;

  const badgeEl = document.getElementById("drawer-agent-badge");
  const card = document.getElementById(`card-${agent}`);
  const cardState = card?.classList.contains("running") ? "running"
    : card?.classList.contains("done") ? "done"
    : card?.classList.contains("error") ? "error"
    : card?.classList.contains("waiting") ? "waiting"
    : "idle";
  badgeEl.className = `badge badge-${cardState}`;
  badgeEl.textContent = AGENT_STATUS_LABELS[cardState]?.() ?? cardState;

  const timeEl = document.getElementById("drawer-agent-time");
  const start = agentStartTimes[agent];
  const end = agentEndTimes[agent];
  if (start && end) {
    timeEl.textContent = fmtDuration(Math.max(0, Math.round((end - start) / 1000)));
  } else if (start) {
    timeEl.textContent = fmtDuration(Math.floor((Date.now() - start) / 1000));
  } else {
    timeEl.textContent = "";
  }

  const stepsEl = document.getElementById("drawer-steps");
  stepsEl.innerHTML = plan.steps.map((step, i) => {
    let cls, icon;
    if (state.done.has(i)) { cls = "step-done"; icon = "✓"; }
    else if (state.active === i) { cls = "step-active"; icon = "⟳"; }
    else { cls = "step-pending"; icon = "○"; }
    const liveLabel = state.labels?.[i];
    const subHtml = liveLabel ? `<span class="step-sub">${escapeHtml(liveLabel)}</span>` : "";
    return `<li class="${cls}"><span class="step-icon">${icon}</span><div class="step-body"><span class="step-name">${escapeHtml(step)}</span>${subHtml}</div></li>`;
  }).join("");

  const outputEl = document.getElementById("drawer-output");
  const rawToggle = document.getElementById("drawer-raw-toggle");
  if (rawToggle) rawToggle.checked = drawerRawMode;
  renderDrawerReasoning(agent);
  if (_agentOutputs[agent]) {
    const updatedAt = currentAgentOutputUpdatedAt[agent];
    const heading = updatedAt
      ? `${escapeHtml(t("drawer.output"))} · ${escapeHtml(formatSavedAt(updatedAt))}`
      : escapeHtml(t("drawer.output"));
    const body = drawerRawMode
      ? escapeHtml(JSON.stringify(_agentOutputs[agent], null, 2))
      : agentOutputHtml(agent, _agentOutputs[agent]);
    outputEl.innerHTML = `<div class="drawer-output-heading">${heading}</div><pre>${body}</pre>`;
  } else {
    outputEl.innerHTML = "";
  }
}

// ── Agent summary queue ───────────────────────────────────────────────────
function enqueueAgentSummary(msg) {
  if (!msg || !msg.agent) return;
  const plan = getAgentPlan(msg.agent);
  agentSummaryQueue.push({
    agent: msg.agent,
    agentLabel: plan?.label || msg.agent,
    title: String(msg.title || t("agentSummary.defaultTitle", { agent: plan?.label || msg.agent })),
    summary: String(msg.summary || ""),
    bullets: Array.isArray(msg.bullets) ? msg.bullets.map((b) => String(b || "").trim()).filter(Boolean) : [],
    ts: msg.ts || "",
  });
  showNextAgentSummary();
}

function showNextAgentSummary() {
  if (activeAgentSummary || agentSummaryQueue.length === 0) return;
  activeAgentSummary = agentSummaryQueue.shift();
  renderAgentSummaryPopup();
}

function renderAgentSummaryPopup() {
  const popup = document.getElementById("agent-summary-popup");
  if (!popup || !activeAgentSummary) return;
  const item = activeAgentSummary;
  const countEl = document.getElementById("agent-summary-count");
  const agentEl = document.getElementById("agent-summary-agent");
  const titleEl = document.getElementById("agent-summary-title");
  const bodyEl = document.getElementById("agent-summary-body");
  const bulletsEl = document.getElementById("agent-summary-bullets");
  const dismissEl = document.getElementById("agent-summary-dismiss");

  if (agentEl) agentEl.textContent = t("agentSummary.agentComplete", { agent: item.agentLabel });
  if (titleEl) titleEl.textContent = item.title;
  if (bodyEl) bodyEl.textContent = item.summary;
  if (bulletsEl) {
    bulletsEl.innerHTML = item.bullets
      .map((bullet) => `<li>${escapeHtml(bullet)}</li>`)
      .join("");
    bulletsEl.classList.toggle("hidden", item.bullets.length === 0);
  }
  if (countEl) {
    countEl.textContent = agentSummaryQueue.length > 0
      ? t("agentSummary.queueCount", { count: agentSummaryQueue.length })
      : t("agentSummary.queueClear");
  }
  if (dismissEl) {
    dismissEl.textContent = agentSummaryQueue.length > 0
      ? t("agentSummary.next")
      : t("agentSummary.dismiss");
  }
  popup.classList.remove("hidden");
  requestAnimationFrame(() => popup.classList.add("visible"));
}

function dismissAgentSummary() {
  const popup = document.getElementById("agent-summary-popup");
  const dismissed = activeAgentSummary;
  activeAgentSummary = null;
  if (popup) {
    popup.classList.remove("visible");
    setTimeout(() => {
      if (!activeAgentSummary) popup.classList.add("hidden");
    }, 180);
  }
  if (dismissed?.agent === "manager" && pendingFinalResult) {
    const finalResult = pendingFinalResult;
    void renderFinalResultOnce(finalResult);
  }
  showNextAgentSummary();
}

function clearAgentSummaryQueue() {
  agentSummaryQueue.length = 0;
  activeAgentSummary = null;
  pendingFinalResult = null;
  finalResultReviewId = null;
  finalResultRenderInFlightId = null;
  const popup = document.getElementById("agent-summary-popup");
  if (popup) {
    popup.classList.remove("visible");
    popup.classList.add("hidden");
  }
}

// ── Browser notifications ─────────────────────────────────────────────────
function requestNotifPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function sendCompletionNotification() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  if (document.hasFocus()) return; // only notify when tab is backgrounded
  const elapsed = _reviewStartTime ? fmtDuration(Math.round((Date.now() - _reviewStartTime) / 1000)) : "";
  const body = elapsed
    ? `${t("notifications.completedIn", { elapsed })}`
    : t("notifications.completed");
  const n = new Notification(t("page.title"), { body });
  n.onclick = () => { window.focus(); n.close(); };
}

function setGlobalStatus(state, detail = "") {
  const el = document.getElementById("global-status");
  el.className = `badge badge-${state}`;
  currentGlobalStatusState = state;
  const labels = {
    idle: t("status.idle"),
    running: t("status.running"),
    waiting: t("status.waiting"),
    done: t("status.done"),
    stopped: t("status.stopped"),
    error: t("status.error"),
  };
  const detailText = String(detail || "").trim();
  el.textContent = state === "error" && detailText
    ? t("status.failedWithReason", { reason: compactStatusDetail(detailText) })
    : labels[state] || state;
  el.title = detailText;
}

function resetCards() {
  // Stop all timers and clear progress state
  currentResultsView = null;
  currentShareArtifact = null;
  for (const k of Object.keys(agentTimerIds)) { clearInterval(agentTimerIds[k]); delete agentTimerIds[k]; }
  for (const k of Object.keys(agentStartTimes)) delete agentStartTimes[k];
  for (const k of Object.keys(agentEndTimes)) delete agentEndTimes[k];
  for (const k of Object.keys(agentStepProgress)) delete agentStepProgress[k];
  for (const k of Object.keys(_agentOutputs)) delete _agentOutputs[k];
  for (const k of Object.keys(currentAgentOutputUpdatedAt)) delete currentAgentOutputUpdatedAt[k];
  for (const k of Object.keys(agentStepHistory)) delete agentStepHistory[k];
  _currentActiveAgent = null;
  _reviewStartTime = Date.now();
  clearAgentSummaryQueue();

  document.querySelectorAll(".agent-card").forEach(card => {
    const agent = card.dataset.agent;
    card.className = "agent-card";
    const body = card.querySelector(".card-body");
    body.innerHTML = "";
    body.classList.add("hidden");
    body.classList.remove("peek");
    body.onclick = null;
    wireAgentCardInteractions(card, agent);
    const label = card.querySelector(".agent-status-label");
    if (label) label.textContent = t("status.idle");
    const elapsed = card.querySelector(".agent-elapsed");
    if (elapsed) elapsed.textContent = "";
    clearStreamLog(agent);
  });

  _drawerPinned = false;
  if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  const pinBtn = document.getElementById("drawer-pin-btn");
  if (pinBtn) {
    pinBtn.classList.remove("pinned");
    pinBtn.setAttribute("aria-label", t("drawer.pin"));
    pinBtn.title = t("drawer.pin");
  }
  const followBar = document.getElementById("drawer-follow-bar");
  if (followBar) { followBar.textContent = t("drawer.autoFollowing"); followBar.classList.remove("pinned-bar"); }
  dataLoaderHistory.length = 0;
  renderDataLoaderHistory();
  setDataLoaderExpanded(false);
  setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.waitingToLoad"), false);
  setButtonBusy(document.getElementById("start-btn"), false);
  setStopButtonRunning(false);
}
