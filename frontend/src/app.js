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

// Browser-side controller for review input, streaming progress, results, and saved history.
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

function todayLocalIso() {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60 * 1000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function ensureReviewDate() {
  const input = document.getElementById("p-date");
  if (!input) return todayLocalIso();
  if (!input.value) input.value = todayLocalIso();
  return input.value;
}

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
let returnToHistoryOnResultsClose = false;
let activeAgentAnalysisTab = "planner";
let feedbackRerunInFlight = false;
let pendingReviewStartBody = null;
let pendingFeedbackMatch = null;
let currentSharePrivacyMode = "masked";
let currentShareArtifact = null;
let currentAgentOutputUpdatedAt = {};
const agentStepHistory = {};

const MAX_STEP_HISTORY = 60;
const MAX_PERSISTED_STEP_LOGS = 25;
const REVIEW_TIMER_TICK_MS = 1000;
let drawerRawMode = false;

const agentStartTimes = {};
const agentEndTimes = {};
const agentTimerIds = {};
const agentStepProgress = {};
const AGENT_CARD_NAMES = new Set(["data","planner","news","risk","regime","theme","validation","manager"]);

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
  planner:    { labelKey:"agents.planner.label", descKey:"agents.planner.desc", stepKeys:["agents.planner.steps.0", "agents.planner.steps.1", "agents.planner.steps.2"] },
  data:       { labelKey:"agents.data.label", descKey:"agents.data.desc", stepKeys:["agents.data.steps.0", "agents.data.steps.1", "agents.data.steps.2", "agents.data.steps.3", "agents.data.steps.4"] },
  news:       { labelKey:"agents.news.label", descKey:"agents.news.desc", stepKeys:["agents.news.steps.0", "agents.news.steps.1", "agents.news.steps.2", "agents.news.steps.3", "agents.news.steps.4"] },
  risk:       { labelKey:"agents.risk.label", descKey:"agents.risk.desc", stepKeys:["agents.risk.steps.0", "agents.risk.steps.1", "agents.risk.steps.2", "agents.risk.steps.3", "agents.risk.steps.4"] },
  regime:     { labelKey:"agents.regime.label", descKey:"agents.regime.desc", stepKeys:["agents.regime.steps.0", "agents.regime.steps.1", "agents.regime.steps.2", "agents.regime.steps.3", "agents.regime.steps.4"] },
  theme:      { labelKey:"agents.theme.label", descKey:"agents.theme.desc", stepKeys:["agents.theme.steps.0", "agents.theme.steps.1", "agents.theme.steps.2"] },
  validation: { labelKey:"agents.validation.label", descKey:"agents.validation.desc", stepKeys:["agents.validation.steps.0"] },
  manager:    { labelKey:"agents.manager.label", descKey:"agents.manager.desc", stepKeys:["agents.manager.steps.0", "agents.manager.steps.1", "agents.manager.steps.2"] },
};

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
const profileTimers = new WeakMap();
const LAST_REVIEW_STORAGE_KEY = "portAdvisorLastReview";
const REVIEW_HISTORY_STORAGE_KEY = "portAdvisorReviewHistory";
const MAX_REVIEW_HISTORY = 30;
const SIDEBAR_WIDTH_STORAGE_KEY = "portAdvisorSidebarWidth";
const SIDEBAR_MIN_PX = 180;
const SIDEBAR_MAX_PX = 560;
const DATA_LOADER_ERROR_RE = /(missing portfolio history for analog matching|missing price history for holdings|yfinance returned no data for analog matching|insufficient historical windows for analog matching)/i;
const DATA_LOADER_HISTORY_MAX = 12;
const STATUS_DETAIL_MAX_CHARS = 64;
const dataLoaderHistory = [];
const dataLoaderTickerStatus = new Map();
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
const PRIORITY_ORDER = ["urgent", "this-week", "next-review", "watch"];
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
const MANAGER_REVIEW_FIELDS = [
  "executive_summary", "actions", "do_nothing_case",
  "portfolio_verdict",
];

const AGENT_MODEL_SLOTS = [
  { id: "planner", labelKey: "agents.planner.label" },
  { id: "news_tools", labelKey: "agents.news.label", hintKey: "llm.agentHints.newsTools" },
  { id: "news_synthesis", labelKey: "agents.news.label", hintKey: "llm.agentHints.newsSynthesis" },
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

function normalizeModelEndpointMap(value) {
  const out = {};
  if (!value || typeof value !== "object" || Array.isArray(value)) return out;
  for (const [model, url] of Object.entries(value)) {
    const cleanModel = model && String(model).trim();
    const cleanUrl = url && String(url).trim();
    if (cleanModel && cleanUrl) out[cleanModel] = cleanUrl;
  }
  return out;
}

let _modelLibrary = [];
// A model can select its own OpenAI-compatible endpoint while sharing the same UI.
let _modelEndpointMap = {};

function setModelLibrary(values) {
  _modelLibrary = mergeModelOptions(values);
}

function setModelEndpointMap(value) {
  _modelEndpointMap = normalizeModelEndpointMap(value);
}

function selectedDefaultModel() {
  return _cfgVal("cfg-llm-model");
}

function rememberEndpointForSelectedModel() {
  const model = selectedDefaultModel();
  const url = _cfgVal("cfg-llm-base-url");
  if (model && url) _modelEndpointMap[model] = url;
}

function applyEndpointForSelectedModel() {
  const model = selectedDefaultModel();
  const url = model ? _modelEndpointMap[model] : "";
  const baseUrlEl = document.getElementById("cfg-llm-base-url");
  if (baseUrlEl && url) baseUrlEl.value = url;
}

function addModelToLibrary(name) {
  const text = name && String(name).trim();
  if (!text) return false;
  if (_modelLibrary.includes(text)) return false;
  _modelLibrary = [..._modelLibrary, text];
  const url = _cfgVal("cfg-llm-base-url");
  if (url) _modelEndpointMap[text] = url;
  renderModelLibrary();
  refreshModelSelectors();
  markModelConfigUnsaved();
  return true;
}

function removeModelFromLibrary(name) {
  const next = _modelLibrary.filter((m) => m !== name);
  if (next.length === _modelLibrary.length) return;
  _modelLibrary = next;
  delete _modelEndpointMap[name];
  renderModelLibrary();
  refreshModelSelectors();
  markModelConfigUnsaved();
}

function renderModelLibrary() {
  const ul = document.getElementById("llm-model-library");
  if (!ul) return;
  ul.innerHTML = "";
  if (!_modelLibrary.length) {
    const empty = document.createElement("li");
    empty.className = "llm-model-library__empty muted-text";
    empty.textContent = t("llm.modelLibraryEmpty");
    ul.appendChild(empty);
    return;
  }
  for (const name of _modelLibrary) {
    const li = document.createElement("li");
    li.className = "llm-model-library__row";
    const span = document.createElement("span");
    span.className = "llm-model-library__name";
    const endpoint = _modelEndpointMap[name];
    span.textContent = endpoint ? `${name} · ${endpoint}` : name;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "llm-model-library__remove";
    btn.setAttribute("aria-label", t("llm.removeModelAria", { name }));
    btn.title = t("llm.removeModelTitle");
    btn.textContent = "×";
    btn.addEventListener("click", () => removeModelFromLibrary(name));
    li.appendChild(span);
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function _populateSelectFromLibrary(sel, currentValue, leadingOption) {
  sel.innerHTML = "";
  if (leadingOption) {
    const o = document.createElement("option");
    o.value = leadingOption.value;
    o.textContent = leadingOption.label;
    sel.appendChild(o);
  }
  for (const m of _modelLibrary) {
    const o = document.createElement("option");
    o.value = m;
    o.textContent = m;
    sel.appendChild(o);
  }
  if (currentValue && !_modelLibrary.includes(currentValue) && currentValue !== leadingOption?.value) {
    const o = document.createElement("option");
    o.value = currentValue;
    o.textContent = `${currentValue} ${t("llm.modelMissingTag")}`;
    o.dataset.missing = "1";
    sel.appendChild(o);
  }
  sel.value = currentValue ?? (leadingOption ? leadingOption.value : "");
}

function refreshModelSelectors() {
  const defaultSel = document.getElementById("cfg-llm-model");
  if (defaultSel) {
    _populateSelectFromLibrary(defaultSel, defaultSel.value, null);
  }
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    _populateSelectFromLibrary(sel, sel.value, {
      value: "",
      label: t("llm.useDefault"),
    });
  });
}

function renderAgentModelSelects(savedAgentModels) {
  const wrap = document.getElementById("llm-agent-model-rows");
  if (!wrap) return;
  wrap.innerHTML = "";
  const saved = savedAgentModels && typeof savedAgentModels === "object" ? savedAgentModels : {};
  for (const slot of AGENT_MODEL_SLOTS) {
    const row = document.createElement("div");
    row.className = "cfg-field cfg-field--agent";

    const lab = document.createElement("label");
    lab.setAttribute("for", `cfg-agent-model-${slot.id}`);
    lab.appendChild(document.createTextNode(t(slot.labelKey)));
    if (slot.hintKey) {
      const sp = document.createElement("span");
      sp.className = "cfg-agent-hint";
      sp.textContent = ` (${t(slot.hintKey)})`;
      lab.appendChild(sp);
    }

    const sel = document.createElement("select");
    sel.className = "cfg-select agent-model-select";
    sel.id = `cfg-agent-model-${slot.id}`;
    sel.dataset.agentKey = slot.id;
    const current = (saved[slot.id] && String(saved[slot.id]).trim()) || "";
    _populateSelectFromLibrary(sel, current, {
      value: "",
      label: t("llm.useDefault"),
    });
    sel.addEventListener("change", () => {
      markModelConfigUnsaved();
      updatePerAgentCount();
    });

    row.appendChild(lab);
    row.appendChild(sel);
    wrap.appendChild(row);
  }
  updatePerAgentCount();
}

function updatePerAgentCount() {
  const el = document.getElementById("llm-per-agent-count");
  if (!el) return;
  const overrides = Array.from(document.querySelectorAll("select.agent-model-select")).filter(
    (sel) => sel.value && sel.value.trim(),
  ).length;
  el.textContent = overrides
    ? t("llm.perAgentCountOverrides", { count: overrides, total: AGENT_MODEL_SLOTS.length })
    : t("llm.perAgentCountAllDefault", { total: AGENT_MODEL_SLOTS.length });
}

function setModelSaveStatus(key, detail = "") {
  const el = document.getElementById("llm-save-status");
  if (!el) return;
  el.dataset.status = key;
  const label = t(`llm.saveStatus.${key}`);
  const textEl = el.querySelector(".llm-save-status-text");
  if (textEl) {
    textEl.textContent = detail ? `${label}: ${detail}` : label;
  } else {
    el.textContent = detail ? `${label}: ${detail}` : label;
  }
  el.title = detail || label;
}

function markModelConfigUnsaved() {
  setModelSaveStatus("unsaved");
}

function collectAgentModelOverrides() {
  const out = {};
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    const k = sel.dataset.agentKey;
    const v = sel.value?.trim();
    if (k && v) out[k] = v;
  });
  return out;
}

function buildLlmOptionalPayload() {
  const out = {};

  const url = _cfgVal("cfg-llm-base-url");
  if (url) out.llm_base_url = url;

  const key = _cfgVal("cfg-llm-api-key");
  if (key) out.llm_api_key = key;

  const defaultModel = _cfgVal("cfg-llm-model");
  if (defaultModel) out.llm_model = defaultModel;

  const am = collectAgentModelOverrides();
  if (Object.keys(am).length) out.agent_models = am;

  return Object.keys(out).length ? out : undefined;
}

async function _readErrorDetail(response) {
  try {
    const body = await response.json();
    if (body && body.detail) return body.detail;
  } catch {
  }
  return `HTTP ${response.status}`;
}

async function saveModelConfig() {
  setModelSaveStatus("saving");
  rememberEndpointForSelectedModel();
  const payload = {
    llm_base_url: _cfgVal("cfg-llm-base-url"),
    llm_model: _cfgVal("cfg-llm-model"),
    model_options: [..._modelLibrary],
    model_base_urls: normalizeModelEndpointMap(_modelEndpointMap),
    model_extra_args: _cfgVal("cfg-model-extra-args"),
    agent_models: collectAgentModelOverrides(),
    search_provider: _cfgVal("cfg-search-provider"),
    searxng_url: _cfgVal("cfg-searxng-url"),
  };
  const apiKey = _cfgVal("cfg-llm-api-key");
  if (apiKey) payload.llm_api_key = apiKey;
  const tavilyKey = _cfgVal("cfg-tavily-key");
  if (tavilyKey) payload.tavily_api_key = tavilyKey;
  try {
    const r = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await _readErrorDetail(r));
    clearSecretFields();
    await loadModelConfigUi("saved");
  } catch (err) {
    setModelSaveStatus("error", err?.message || String(err));
  }
}

function clearSecretFields() {
  for (const id of ["cfg-llm-api-key", "cfg-tavily-key"]) {
    const el = document.getElementById(id);
    if (el) el.value = "";
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
    }
    if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
    setModelSaveStatus(body.ok ? "connected" : "testFailed", body.message || "");
  } catch (err) {
    setModelSaveStatus("testFailed", err?.message || String(err));
  }
}

async function testSearchConnection() {
  setModelSaveStatus("testing");
  try {
    const payload = {
      search_provider: _cfgVal("cfg-search-provider"),
      searxng_url: _cfgVal("cfg-searxng-url"),
    };
    const tavilyKey = _cfgVal("cfg-tavily-key");
    if (tavilyKey) payload.tavily_api_key = tavilyKey;
    const r = await fetch("/api/config/search/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let body = {};
    try {
      body = await r.json();
    } catch {
    }
    if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
    setModelSaveStatus(body.ok ? "connected" : "testFailed", body.message || "");
  } catch (err) {
    setModelSaveStatus("testFailed", err?.message || String(err));
  }
}

async function resetModelConfig() {
  setModelSaveStatus("saving");
  try {
    const r = await fetch("/api/config", { method: "DELETE" });
    if (!r.ok) throw new Error(await _readErrorDetail(r));
    clearSecretFields();
    await loadModelConfigUi("reset");
  } catch (err) {
    setModelSaveStatus("error", err?.message || String(err));
  }
}

async function loadModelConfigUi(statusKey = "loaded") {
  let server = {};
  let serverFetchOk = false;
  try {
    const r = await fetch("/api/config");
    if (r.ok) {
      server = await r.json();
      serverFetchOk = true;
    }
  } catch {
  }

  setModelLibrary(mergeModelOptions(server.model_options, server.llm_model));
  setModelEndpointMap(server.model_base_urls);
  if (server.llm_model && server.llm_base_url && !_modelEndpointMap[server.llm_model]) {
    _modelEndpointMap[server.llm_model] = server.llm_base_url;
  }
  renderModelLibrary();

  const defaultSel = document.getElementById("cfg-llm-model");
  if (defaultSel) {
    const defaultValue = server.llm_model || _modelLibrary[0] || "";
    _populateSelectFromLibrary(defaultSel, defaultValue, null);
  }

  renderAgentModelSelects(server.default_agent_models);

  const extraArgsEl = document.getElementById("cfg-model-extra-args");
  if (extraArgsEl) extraArgsEl.value = server.model_extra_args || "";

  const baseUrlEl = document.getElementById("cfg-llm-base-url");
  if (baseUrlEl) baseUrlEl.value = server.llm_base_url || "";

  const providerSel = document.getElementById("cfg-search-provider");
  if (providerSel) providerSel.value = server.search_provider || "searxng";

  const searxngEl = document.getElementById("cfg-searxng-url");
  if (searxngEl) searxngEl.value = server.searxng_url || "";

  setModelSaveStatus(serverFetchOk ? statusKey : "loadFailed");

  if (!loadModelConfigUi._inputsWired) {
    loadModelConfigUi._inputsWired = true;
    const wireInput = (id) =>
      document.getElementById(id)?.addEventListener("input", markModelConfigUnsaved);
    [
      "cfg-llm-base-url",
      "cfg-llm-api-key",
      "cfg-model-extra-args",
      "cfg-searxng-url",
      "cfg-tavily-key",
    ].forEach(wireInput);
    document.getElementById("cfg-llm-base-url")?.addEventListener("input", () => {
      rememberEndpointForSelectedModel();
      renderModelLibrary();
    });
    document.getElementById("cfg-llm-model")?.addEventListener("change", () => {
      applyEndpointForSelectedModel();
      markModelConfigUnsaved();
    });
    document
      .getElementById("cfg-search-provider")
      ?.addEventListener("change", markModelConfigUnsaved);
    document.getElementById("llm-save-config")?.addEventListener("click", saveModelConfig);
    document.getElementById("llm-test-config")?.addEventListener("click", testModelConnection);
    document.getElementById("search-test-config")?.addEventListener("click", testSearchConnection);
    document.getElementById("llm-reset-config")?.addEventListener("click", resetModelConfig);

    const addInput = document.getElementById("cfg-add-model-input");
    const addBtn = document.getElementById("cfg-add-model-btn");
    const submitAdd = () => {
      if (!addInput) return;
      const added = addModelToLibrary(addInput.value);
      if (added) addInput.value = "";
    };
    addBtn?.addEventListener("click", submitAdd);
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

}

let _reviewStartTime = null;
let _reviewEndTime = null;
let _reviewTimerId = null;
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

function fmtAgentRunTime(totalSecs) {
  return t("agents.runTime", { duration: fmtDuration(totalSecs) });
}

function reviewElapsedSeconds(nowMs = Date.now()) {
  if (!_reviewStartTime) return 0;
  const endMs = _reviewEndTime || nowMs;
  return Math.max(0, Math.floor((endMs - _reviewStartTime) / 1000));
}

function renderReviewElapsed() {
  const el = document.getElementById("review-elapsed-value");
  if (!el) return;
  el.textContent = _reviewStartTime
    ? fmtDuration(reviewElapsedSeconds())
    : t("sidebar.timeNotStarted");
}

function startReviewElapsedTimer() {
  if (_reviewTimerId) {
    clearInterval(_reviewTimerId);
    _reviewTimerId = null;
  }
  _reviewStartTime = Date.now();
  _reviewEndTime = null;
  renderReviewElapsed();
  _reviewTimerId = setInterval(renderReviewElapsed, REVIEW_TIMER_TICK_MS);
}

function stopReviewElapsedTimer() {
  if (!_reviewStartTime) return;
  _reviewEndTime = Date.now();
  if (_reviewTimerId) {
    clearInterval(_reviewTimerId);
    _reviewTimerId = null;
  }
  renderReviewElapsed();
}

function clearReviewElapsedTimer() {
  if (_reviewTimerId) {
    clearInterval(_reviewTimerId);
    _reviewTimerId = null;
  }
  _reviewStartTime = null;
  _reviewEndTime = null;
  renderReviewElapsed();
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
    if (agent === "data") setDataLoaderTickerResult(payload);
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
      stopReviewElapsedTimer();
      setGlobalStatus("stopped");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.reviewStopped"), false);
    } else if (data.status === "done") {
      stopReviewElapsedTimer();
      setGlobalStatus("done");
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      await renderFinalResultOnce({
        output: data.agent_outputs?.manager,
        reviewId,
      });
    } else if (data.status === "error") {
      stopReviewElapsedTimer();
      const err = data.last_error && typeof data.last_error === "object" ? data.last_error : {};
      const message = String(err.message || t("dataLoader.reviewFailed"));
      const failureDetail = isDataLoaderError(message)
        ? formatDataLoaderError(message)
        : message;
      setGlobalStatus("error", failureDetail);
      setButtonBusy(document.getElementById("start-btn"), false);
      setStopButtonRunning(false);
      const failedAgent = err.agent || _currentActiveAgent;
      if (failedAgent) setCardState(failedAgent, "error", failureDetail);
      setDataLoaderStatus("error", failureDetail, isDataLoaderError(message), { recordHistory: false });
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
    }, 320);
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

function dataLoaderTickerStatusLabel(state) {
  const labels = {
    queued: t("dataLoader.tickerQueued"),
    loading: t("dataLoader.tickerLoading"),
    loaded: t("dataLoader.tickerLoaded"),
    error: t("dataLoader.tickerError"),
  };
  return labels[state] || state;
}

function normalizeTickerList(tickers) {
  const out = [];
  const seen = new Set();
  for (const ticker of tickers || []) {
    const value = String(ticker || "").trim().toUpperCase();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

function initializeDataLoaderTickerStatus(positions) {
  dataLoaderTickerStatus.clear();
  for (const ticker of normalizeTickerList((positions || []).map((p) => p?.ticker))) {
    dataLoaderTickerStatus.set(ticker, "queued");
  }
  renderDataLoaderHistory();
}

function setAllDataLoaderTickers(state) {
  for (const ticker of dataLoaderTickerStatus.keys()) {
    dataLoaderTickerStatus.set(ticker, state);
  }
  renderDataLoaderHistory();
}

function setDataLoaderTickers(state, tickers) {
  for (const ticker of normalizeTickerList(tickers)) {
    if (dataLoaderTickerStatus.has(ticker)) {
      dataLoaderTickerStatus.set(ticker, state);
    }
  }
  renderDataLoaderHistory();
}

function setDataLoaderTickerResult(output) {
  const marketData = output?.market_data || output;
  const loadedTickers = (marketData?.positions || []).map((position) => position?.ticker);
  const erroredTickers = marketData?.errors || [];
  setAllDataLoaderTickers("error");
  setDataLoaderTickers("loaded", loadedTickers);
  setDataLoaderTickers("error", erroredTickers);
}

function dataLoaderTickerStatusClass(state) {
  const safeState = ["queued", "loading", "loaded", "error"].includes(state) ? state : "queued";
  return `data-loader-ticker-state data-loader-ticker-state-${safeState}`;
}

function renderDataLoaderHistory() {
  const list = document.getElementById("data-loader-history");
  if (!list) return;
  if (dataLoaderTickerStatus.size === 0) {
    list.innerHTML = `<li class="data-loader-empty">${escapeHtml(t("dataLoader.noTickerStatusYet"))}</li>`;
    return;
  }
  list.innerHTML = Array.from(dataLoaderTickerStatus.entries())
    .map(([ticker, state]) => `
      <li>
        <span class="data-loader-ticker-symbol">${escapeHtml(ticker)}</span>
        <span class="${dataLoaderTickerStatusClass(state)}">${escapeHtml(dataLoaderTickerStatusLabel(state))}</span>
      </li>`)
    .join("");
}

function setDataLoaderExpanded(expanded) {
  const toggle = document.getElementById("card-data");
  const body = document.getElementById("data-loader-expanded");
  if (!toggle || !body) return;
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  toggle.setAttribute("title", expanded ? t("dataLoader.hideDetails") : t("dataLoader.showDetails"));
  body.classList.toggle("hidden", !expanded);
  if (expanded) renderDataLoaderHistory();
}

function toggleDataLoaderExpanded() {
  const toggle = document.getElementById("card-data");
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
  setCardState("data", state, state === "error" ? text : "");
  if (badge) {
    const labels = {
      idle: t("status.idle"),
      running: t("status.running"),
      done: t("status.done"),
      error: t("status.error"),
    };
    badge.textContent = labels[state] || state;
    badge.title = text;
    if (!badge.classList.contains("agent-status-label")) {
      badge.className = `badge badge-${state}`;
    }
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
  const sign = n >= 0 ? "+" : "-";
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

function toFiniteNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v, digits = 2, signed = false) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const sign = n < 0 ? "-" : (signed ? "+" : "");
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function fmtPctFromRatio(v, digits = 1) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const pct = n * 100;
  const sign = pct >= 0 ? "+" : "-";
  return `${sign}${formatNumber(Math.abs(pct), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
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

function scheduleProfileFetch(wrap) {
  const prev = profileTimers.get(wrap);
  if (prev) clearTimeout(prev);
  profileTimers.set(wrap, setTimeout(() => fetchProfileForCard(wrap), 420));
}

async function fetchProfileForCard(wrap) {
  const tickerInput = wrap.querySelector('[data-field="ticker"]');
  const nameInput = wrap.querySelector('[data-field="name"]');
  const sectorInput = wrap.querySelector('[data-field="sector"]');
  if (!tickerInput || !nameInput || !sectorInput) return;

  const ticker = tickerInput.value.trim().toUpperCase();
  if (!ticker || (nameInput.value.trim() && sectorInput.value.trim())) return;

  wrap.dataset.profileTicker = ticker;
  try {
    const res = await fetch(`/api/market/profile/${encodeURIComponent(ticker)}`);
    if (!res.ok) throw new Error("bad");
    const profile = await res.json();
    const currentTicker = tickerInput.value.trim().toUpperCase();
    if (currentTicker !== ticker || wrap.dataset.profileTicker !== ticker) return;

    const name = String(profile?.name || "").trim();
    const sector = String(profile?.sector || "").trim();
    if (!nameInput.value.trim() && name) nameInput.value = name;
    if (!sectorInput.value.trim() && sector) sectorInput.value = sector;
  } catch {
  }
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
    params.set("actions_start", ensureReviewDate());
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
  return positionRowsMissingReadyQuoteElements()
    .map((wrap) => wrap.querySelector('[data-field="ticker"]')?.value?.trim()?.toUpperCase())
    .filter(Boolean);
}

function positionRowsMissingReadyQuoteElements() {
  return Array.from(document.querySelectorAll("#positions-body .position-row-wrap"))
    .filter((wrap) => {
      const ticker = wrap.querySelector('[data-field="ticker"]')?.value?.trim();
      if (!ticker) return false;
      const quantity = parseFloat(wrap.querySelector('[data-field="quantity"]')?.value);
      if (Number.isNaN(quantity) || quantity <= 0) return false;
      return Number.isNaN(getLastPrice(wrap));
    });
}

async function refreshMissingQuotesForReview() {
  const missingRows = positionRowsMissingReadyQuoteElements();
  if (missingRows.length === 0) return [];

  const startBtn = document.getElementById("start-btn");
  setButtonBusy(startBtn, true, t("buttons.refreshMarketData"));
  try {
    showToast(t("review.marketDataRefreshing"));
    await Promise.all(missingRows.map((wrap) => fetchQuoteForCard(wrap)));
  } finally {
    setButtonBusy(startBtn, false);
    refreshPositionsState();
  }
  return positionRowsMissingReadyQuotes();
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
    tickerEl.addEventListener("blur", () => {
      fetchProfileForCard(wrap);
      fetchQuoteForCard(wrap);
    });
    tickerEl.addEventListener("input", () => {
      scheduleProfileFetch(wrap);
      scheduleQuoteFetch(wrap);
    });
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
  header.setAttribute("aria-expanded", card.classList.contains("steps-open") ? "true" : "false");
  header.setAttribute("aria-controls", `card-${agent}-steps`);
  header.onclick = () => toggleAgentStepStatus(agent);
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
  document.querySelectorAll(".agent-card.steps-open").forEach((card) => {
    if (card.dataset.agent) renderAgentStepStatus(card.dataset.agent);
  });
  refreshPositionsState();
  updateWeightSummary();
  setGlobalStatus(currentGlobalStatusState);
  renderReviewElapsed();
  document.querySelectorAll(".agent-card").forEach((card) => {
    const agent = card.dataset.agent;
    if (agent && agentStartTimes[agent]) renderAgentElapsed(agent);
  });
  setDataLoaderStatus(
    currentDataLoaderUi.state,
    currentDataLoaderDetailInput(),
    currentDataLoaderUi.allowRetry,
    { recordHistory: false },
  );
  renderDataLoaderHistory();
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
  const weightCol = document.querySelector(".positions-head-row span:nth-child(4)");
  if (weightCol) weightCol.textContent = t("positions.weightPercent");

  updateWeightSummary();

  document.getElementById("add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("empty-add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("restore-sample-btn")?.addEventListener("click", restoreDefaultPositions);
  document.getElementById("portfolio-csv-input")?.addEventListener("change", handlePortfolioCsvImport);
  document.getElementById("save-portfolio-btn")?.addEventListener("click", savePortfolioCsv);
  document.getElementById("refresh-quotes-btn")?.addEventListener("click", () => refreshAllQuotes());
  document.getElementById("start-btn")?.addEventListener("click", startReview);
  document.getElementById("stop-btn")?.addEventListener("click", stopReview);
  document.getElementById("retry-review-btn")?.addEventListener("click", retryLastReview);
  document.getElementById("card-data")?.addEventListener("click", (e) => {
    if (e.target?.closest?.("button")) return;
    toggleDataLoaderExpanded();
  });
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
  document.getElementById("past-feedback-modal-close")?.addEventListener("click", hidePastFeedbackModal);
  document.getElementById("past-feedback-modal-backdrop")?.addEventListener("click", hidePastFeedbackModal);
  document.getElementById("past-feedback-skip")?.addEventListener("click", runPendingReviewWithoutFeedback);
  document.getElementById("past-feedback-include")?.addEventListener("click", runPendingReviewWithFeedback);
  document.getElementById("drawer-raw-toggle")?.addEventListener("change", (e) => {
    drawerRawMode = Boolean(e.target?.checked);
    if (_drawerOpen && _drawerAgent) renderDrawer(_drawerAgent);
  });
  document.getElementById("results-modal-close")?.addEventListener("click", hideResultsModal);
  document.getElementById("results-modal-backdrop")?.addEventListener("click", hideResultsModal);
  document.getElementById("open-agent-analysis")?.addEventListener("click", showAgentAnalysisModal);
  document.getElementById("agent-analysis-modal-close")?.addEventListener("click", hideAgentAnalysisModal);
  document.getElementById("agent-analysis-modal-backdrop")?.addEventListener("click", hideAgentAnalysisModal);
  wireAgentAnalysisControls();
  document.getElementById("agent-summary-dismiss")?.addEventListener("click", dismissAgentSummary);
  document.getElementById("agent-summary-close")?.addEventListener("click", dismissAgentSummary);
  document.getElementById("drawer-close-btn")?.addEventListener("click", closeDrawer);
  document.getElementById("drawer-pin-btn")?.addEventListener("click", togglePin);
  document.getElementById("agent-drawer-backdrop")?.addEventListener("click", closeDrawer);
  document.querySelectorAll(".agent-card").forEach(card => {
    const agent = card.dataset.agent;
    if (agent === "data") return;
    wireAgentCardInteractions(card, agent);
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
  initializeDataLoaderTickerStatus([]);
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

  wrap.innerHTML = `
    <div class="position-row">
      <button type="button" class="btn-assert-toggle" aria-expanded="false" aria-label="${escapeHtml(t("positions.row.showAssertion"))}" title="${escapeHtml(t("positions.row.assertionTitle"))}" data-i18n-aria-label="positions.row.showAssertion" data-i18n-title="positions.row.assertionTitle">▸</button>
      <input type="text" data-field="ticker" class="pc-ticker" value="${tickerValue}" placeholder="${escapeHtml(t("positions.row.tickerPlaceholder"))}" autocomplete="off" title="${escapeHtml(t("positions.row.tickerTitle"))}" data-i18n-placeholder="positions.row.tickerPlaceholder" data-i18n-title="positions.row.tickerTitle" />
      <input type="text" data-field="name" value="${n}" placeholder="${escapeHtml(t("positions.row.namePlaceholder"))}" title="${escapeHtml(t("positions.row.nameTitle"))}" data-i18n-placeholder="positions.row.namePlaceholder" data-i18n-title="positions.row.nameTitle" />
      <span data-ro="weight" class="row-metric muted" title="${escapeHtml(t("positions.row.weightTitle"))}" data-i18n-title="positions.row.weightTitle">0.0%</span>
      <input type="text" data-field="sector" value="${s}" placeholder="${escapeHtml(t("positions.row.sectorPlaceholder"))}" title="${escapeHtml(t("positions.row.sectorTitle"))}" data-i18n-placeholder="positions.row.sectorPlaceholder" data-i18n-title="positions.row.sectorTitle" />
      <span data-ro="price" class="row-metric muted" title="${escapeHtml(t("positions.row.priceTitle"))}" data-i18n-title="positions.row.priceTitle">—</span>
      <input type="number" data-field="quantity" step="0.0001" value="${qty}" placeholder="${escapeHtml(t("positions.row.quantityPlaceholder"))}" title="${escapeHtml(t("positions.row.quantityTitle"))}" data-i18n-placeholder="positions.row.quantityPlaceholder" data-i18n-title="positions.row.quantityTitle" />
      <span data-ro="value" class="row-metric muted" title="${escapeHtml(t("positions.row.valueTitle"))}" data-i18n-title="positions.row.valueTitle">—</span>
      <span data-ro="ret-1m" class="row-metric muted" title="${escapeHtml(t("positions.row.month1Title"))}" data-i18n-title="positions.row.month1Title">—</span>
      <span data-ro="ret-1y" class="row-metric muted" title="${escapeHtml(t("positions.row.year1Title"))}" data-i18n-title="positions.row.year1Title">—</span>
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
  fetchProfileForCard(wrap);
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
  document.getElementById("p-date").value = meta.review_date || todayLocalIso();
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
    asset_class: "equity",
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
  const reviewDate = ensureReviewDate();
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
      asset_class: "equity",
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
    review_date: reviewDate,
    context_note: document.getElementById("p-context").value.trim(),
    positions,
    base_currency: "USD",
  };
}

async function fetchPastFeedbackMatch(portfolio) {
  try {
    const res = await fetch("/api/reviews/feedback-candidates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data?.match?.items?.length ? data.match : null;
  } catch {
    return null;
  }
}

function renderPastFeedbackMatch(match) {
  const list = document.getElementById("past-feedback-list");
  const source = document.getElementById("past-feedback-source");
  if (!list || !source) return;
  source.textContent = t("pastFeedback.source", {
    portfolio: match.portfolio_name || t("common.portfolio"),
    date: formatSavedAt(match.saved_at),
  });
  list.innerHTML = match.items.map((item, index) => `
    <label class="past-feedback-item">
      <input type="checkbox" value="${escapeHtml(item.round_id || String(index))}" data-feedback-index="${index}" ${index < 3 ? "checked" : ""} />
      <span>
        <strong>${escapeHtml(t("pastFeedback.itemLabel", { count: index + 1 }))}</strong>
        <span>${escapeHtml(item.comment || "")}</span>
        ${item.submitted_at ? `<small>${escapeHtml(formatSavedAt(item.submitted_at))}</small>` : ""}
      </span>
    </label>
  `).join("");
}

function showPastFeedbackModal(startBody, match) {
  pendingReviewStartBody = cloneReviewBody(startBody);
  pendingFeedbackMatch = match;
  renderPastFeedbackMatch(match);
  const modal = document.getElementById("past-feedback-modal");
  modal?.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("past-feedback-include")?.focus();
}

function hidePastFeedbackModal() {
  document.getElementById("past-feedback-modal")?.classList.add("hidden");
  pendingReviewStartBody = null;
  pendingFeedbackMatch = null;
  document.body.style.overflow = "";
}

async function launchPendingReview(inheritedFeedback) {
  const startBody = pendingReviewStartBody;
  if (!startBody) return;
  document.getElementById("past-feedback-modal")?.classList.add("hidden");
  pendingReviewStartBody = null;
  pendingFeedbackMatch = null;
  document.body.style.overflow = "";
  startBody.inherited_feedback = inheritedFeedback;
  lastStartBody = cloneReviewBody(startBody);
  await runReviewWithBody(startBody);
}

function runPendingReviewWithoutFeedback() {
  void launchPendingReview([]);
}

function runPendingReviewWithFeedback() {
  const items = pendingFeedbackMatch?.items || [];
  const selected = Array.from(
    document.querySelectorAll("#past-feedback-list input[type='checkbox']:checked"),
  ).map((input) => items[Number(input.dataset.feedbackIndex)]).filter(Boolean);
  void launchPendingReview(selected);
}

async function startReview() {
  let portfolio = buildPortfolio();
  if (portfolio.positions.length === 0) {
    showToast(t("review.addTickerFirst"), true);
    return;
  }

  let missingQuotes = positionRowsMissingReadyQuotes();
  if (missingQuotes.length > 0) {
    missingQuotes = await refreshMissingQuotesForReview();
    if (missingQuotes.length > 0) {
      showToast(t("review.marketDataRequired", { tickers: missingQuotes.join(", ") }), true, 9000);
      return;
    }
    portfolio = buildPortfolio();
  }

  const startBody = { portfolio, locale: getLocale() };
  const feedbackMatch = await fetchPastFeedbackMatch(portfolio);
  if (feedbackMatch) {
    showPastFeedbackModal(startBody, feedbackMatch);
    return;
  }
  lastStartBody = cloneReviewBody(startBody);
  await runReviewWithBody(startBody);
}

async function runReviewWithBody(startBody, options = {}) {
  const fromRetry = Boolean(options.fromRetry);
  resetCards();
  startReviewElapsedTimer();
  initializeDataLoaderTickerStatus(startBody?.portfolio?.positions || []);
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
    stopReviewElapsedTimer();
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
    } catch {  }
    showToast(t("review.startReviewError", { detail }), true);
    stopReviewElapsedTimer();
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
    stopReviewElapsedTimer();
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
    if (snapshot?.status === "done" || snapshot?.status === "stopped" || snapshot?.status === "error") {
      return;
    }
    if (currentGlobalStatusState === "error") return;
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
        setAllDataLoaderTickers("loading");
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
      if (msg.agent === "data") {
        setDataLoaderTickerResult(msg.output);
        setDataLoaderStatus("done", dataLoaderDetail("dataLoader.marketDataLoaded"), false);
      }
      refreshDrawer(msg.agent);
      _currentActiveAgent = null;
      drawerAutoFollowDelayed(msg.agent);
      if (msg.agent === "manager") {
        pendingFinalResult = { output: msg.output, reviewId: currentReviewId };
        void renderFinalResultOnce(pendingFinalResult);
        stopReviewElapsedTimer();
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
        stopReviewElapsedTimer();
        const failureDetail = isDataLoaderError(msg.message)
          ? formatDataLoaderError(msg.message)
          : String(msg.message || t("dataLoader.reviewFailed"));
        setGlobalStatus("error", failureDetail);
        const failedAgent = msg.agent || _currentActiveAgent;
        if (failedAgent) {
          setCardState(failedAgent, "error", failureDetail);
        }
        if (failedAgent === "data") {
          setAllDataLoaderTickers("error");
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
      stopReviewElapsedTimer();
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
  const stepsOpen = card.classList.contains("steps-open");
  const loaderClass = card.classList.contains("data-loader-panel") ? " data-loader-panel" : "";
  card.className = `agent-card ${state}${loaderClass}${stepsOpen ? " steps-open" : ""}`;
  const label = card.querySelector(".agent-status-label");
  if (label) {
    const detailText = String(detail || "").trim();
    label.textContent = state === "error" && detailText
      ? compactStatusDetail(detailText)
      : AGENT_STATUS_LABELS[state]?.() ?? state;
    label.title = detailText;
  }
  if (stepsOpen) renderAgentStepStatus(agent);
}

function markRunningCardsErrored() {
  document.querySelectorAll(".agent-card.running").forEach((card) => {
    const agent = card.dataset.agent;
    if (!agent) return;
    stopElapsedTimer(agent);
    setCardState(agent, "error");
  });
}

function actionTypeLabel(value) {
  return t(`actionType.${normalizeActionType(value)}`);
}

function priorityLabel(value) {
  return t(`priority.${normalizePriority(value)}`);
}

function hasMeaningfulPortfolioVerdict(verdict) {
  if (!verdict || typeof verdict !== "object") return false;
  const hasDetail = [
    "investment_horizon",
    "horizon_detail",
    "primary_risk",
    "recommended_posture",
    "revisit_trigger",
    "rationale",
  ].some(
    (field) => String(verdict[field] || "").trim()
  );
  return (
    hasDetail ||
    normalizePriority(verdict.action_timing) !== "watch"
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

function topPriorityActions(actions) {
  if (!actions.length) return [];
  const bestRank = Math.min(
    ...actions.map((action) => {
      const idx = PRIORITY_ORDER.indexOf(normalizePriority(action.priority));
      return idx === -1 ? PRIORITY_ORDER.length : idx;
    }),
  );
  return actions.filter((action) => {
    const idx = PRIORITY_ORDER.indexOf(normalizePriority(action.priority));
    return (idx === -1 ? PRIORITY_ORDER.length : idx) === bestRank;
  });
}

function formatTopActionSummary(actions) {
  const topActions = topPriorityActions(actions);
  if (!topActions.length) return t("share.noImmediateAction");
  const grouped = new Map();
  for (const action of topActions) {
    const type = actionTypeLabel(action.action_type);
    const position = String(action.position || "").trim();
    if (!position) {
      grouped.set(type, null);
      continue;
    }
    if (grouped.get(type) === null) continue;
    const positions = grouped.get(type) || [];
    positions.push(position);
    grouped.set(type, positions);
  }
  return Array.from(grouped.entries())
    .map(([type, positions]) => positions ? `${type} ${positions.join(", ")}` : type)
    .join("; ");
}

function topActionDirection(actionType) {
  const type = normalizeActionType(actionType);
  if (type === "reduce" || type === "exit") return "sell";
  if (type === "add") return "buy";
  if (type === "rotate" || type === "hedge") return "shift";
  return "passive";
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
    top.setAttribute("role", "button");
    top.setAttribute("tabindex", "0");

    const rank = document.createElement("span");
    rank.className = "action-card__rank";
    rank.textContent = String(index + 1).padStart(2, "0");

    const chips = document.createElement("div");
    chips.className = "action-card__chips";
    const priorityChip = document.createElement("span");
    priorityChip.className = `table-chip priority-chip priority-${priority}`;
    priorityChip.textContent = priorityLabel(priority);
    const actionChip = document.createElement("span");
    actionChip.className = `table-chip action-chip action-${topActionDirection(actionType)}`;
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

    const toggle = document.createElement("span");
    toggle.className = "action-card__toggle";
    toggle.setAttribute("aria-hidden", "true");
    top.append(rank, chips, target, title, toggle);

    const memo = document.createElement("div");
    memo.className = "action-card__memo";
    const memoId = `action-card-memo-${index}`;
    memo.id = memoId;
    memo.hidden = true;
    top.setAttribute("aria-expanded", "false");
    top.setAttribute("aria-controls", memoId);
    top.setAttribute("aria-label", `${t("results.showActionDetails")}: ${title.textContent}`);
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
    const setExpanded = (expanded) => {
      memo.hidden = !expanded;
      article.classList.toggle("action-card--expanded", expanded);
      top.setAttribute("aria-expanded", expanded ? "true" : "false");
      top.setAttribute(
        "aria-label",
        `${expanded ? t("results.hideActionDetails") : t("results.showActionDetails")}: ${title.textContent}`
      );
    };
    top.addEventListener("click", () => {
      setExpanded(top.getAttribute("aria-expanded") !== "true");
    });
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
  const priorityRank = (value) => {
    const idx = PRIORITY_ORDER.indexOf(normalizePriority(value));
    return idx === -1 ? PRIORITY_ORDER.length : idx;
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
    `${t("share.actionTiming")}: ${receipt.actionTiming || t("share.na")}`,
    `${t("share.investmentHorizon")}: ${receipt.investmentHorizon || t("share.na")}`,
    `${t("share.hiddenRisk")}: ${receipt.primaryRisk || t("share.na")}`,
  ];
  if (receipt.worstReplay) lines.push(`${t("share.worstReplay")}: ${receipt.worstReplay}`);
  lines.push(`${t("share.topAction")}: ${receipt.topAction || t("share.noImmediateAction")}`);
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

  const verdict = manager.portfolio_verdict || {};
  const horizonText = [verdict.investment_horizon, verdict.horizon_detail].filter(Boolean).join(", ");
  const verdictLines = [
    `- Action timing: ${priorityLabel(verdict.action_timing)}`,
    horizonText ? `- Investment horizon: ${horizonText}` : "",
    verdict.primary_risk ? `- Primary risk: ${verdict.primary_risk}` : "",
    verdict.recommended_posture ? `- Recommended posture: ${verdict.recommended_posture}` : "",
    verdict.revisit_trigger ? `- Revisit trigger: ${verdict.revisit_trigger}` : "",
    verdict.rationale ? `- Rationale: ${verdict.rationale}` : "",
  ].filter(Boolean);
  if (verdictLines.length) sections.push(`## Portfolio Verdict\n\n${verdictLines.join("\n")}`);

  const riskLines = markdownList(
    []
      .concat(risk?.top_risks || [])
      .concat(risk?.concentration_issues || []),
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
  const verdict = manager?.portfolio_verdict || {};
  const topAction = topPriorityActions(actions)[0];
  const generatedAt = bundle?.savedAt || new Date().toISOString();
  const primaryRisk = firstText(
    verdict.primary_risk,
    firstArrayItem(validation?.critical_issues, "issue"),
    firstArrayItem(risk?.top_risks),
    manager?.executive_summary,
  );
  const investmentHorizon = [verdict.investment_horizon, verdict.horizon_detail]
    .filter(Boolean)
    .join(", ");

  const artifact = {
    receipt: {
      actionTiming: priorityLabel(verdict.action_timing || topAction?.priority),
      investmentHorizon,
      primaryRisk,
      worstReplay: formatWorstReplay(risk, regime, validation),
      topAction: formatTopActionSummary(actions),
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
  setElementText("receipt-action-timing", applySharePrivacy(receipt.actionTiming, view, currentSharePrivacyMode));
  setElementText("receipt-investment-horizon", applySharePrivacy(receipt.investmentHorizon, view, currentSharePrivacyMode));
  setElementText("receipt-primary-risk", applySharePrivacy(receipt.primaryRisk || t("share.na"), view, currentSharePrivacyMode));
  setElementText("receipt-worst-replay", applySharePrivacy(receipt.worstReplay || t("share.na"), view, currentSharePrivacyMode));
  setElementText("receipt-top-action", applySharePrivacy(receipt.topAction || t("share.noImmediateAction"), view, currentSharePrivacyMode));
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

  const ITEM_CAP = 5;
  const moreSpan = (total, sep = " ") => total > ITEM_CAP
    ? `${sep}<span class="muted-text">${escapeHtml(t("agentOutput.andMore", { count: total - ITEM_CAP }))}</span>`
    : "";

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
      const themesList = data.market_themes || [];
      const themes = themesList.slice(0, ITEM_CAP).map(escapeHtml).join(" · ");
      const evtsList = data.key_events || [];
      const evts = evtsList.slice(0, ITEM_CAP).map(escapeHtml).join("; ");
      chunks.push(
        `<b>${escapeHtml(t("agentOutput.news.macro"))}</b> ${escapeHtml(macro)}${macro.length >= 200 ? "…" : ""}`,
        themes ? `<b>${escapeHtml(t("agentOutput.news.themes"))}</b> ${themes}${moreSpan(themesList.length)}` : "",
        evts ? `<b>${escapeHtml(t("agentOutput.news.keyEvents"))}</b> ${evts}${moreSpan(evtsList.length)}` : "",
        data.summary ? `<b>${escapeHtml(t("agentOutput.news.summary"))}</b> ${escapeHtml(data.summary)}` : "",
      );
      return chunks.filter(Boolean).join("<br><br>");
    }
    case "risk": {
      const data = Array.isArray(out.risk_results) ? out.risk_results[0] : out;
      const sortedEntries = (obj, byAbs) => obj && typeof obj === "object"
        ? Object.entries(obj).sort((a, b) => {
            const x = Number(a[1]) || 0, y = Number(b[1]) || 0;
            return byAbs ? Math.abs(y) - Math.abs(x) : y - x;
          })
        : [];

      const flEntries = sortedEntries(data.factor_loadings, true);
      const fl = flEntries.slice(0, ITEM_CAP).map(([k, v]) => `${escapeHtml(k)} ${fmtNum(v, 2, true)}`).join(" · ");
      const frcEntries = sortedEntries(data.factor_risk_contribution, false);
      const frc = frcEntries.slice(0, ITEM_CAP).map(([k, v]) => `${escapeHtml(k)} ${fmtPctFromRatio(v, 1)}`).join(" · ");
      const mrtEntries = sortedEntries(data.marginal_risk_by_ticker, false);
      const mrt = mrtEntries.slice(0, ITEM_CAP).map(([k, v]) => `${escapeHtml(k)} ${fmtPctFromRatio(v, 1)}`).join(" · ");

      const trList = data.top_risks || [];
      const tr = trList.slice(0, ITEM_CAP).map(escapeHtml).join("; ");
      const concList = data.concentration_issues || [];
      const conc = concList.slice(0, ITEM_CAP).map(escapeHtml).join("; ");
      const scenList = data.scenario_losses || [];
      const scen = scenList.slice(0, ITEM_CAP)
        .map((s) => `  • ${escapeHtml(s.scenario || t("agentOutput.risk.scenarioFallback"))}: ${fmtNum(s.estimated_portfolio_loss_pct, 1, true)}%`)
        .join("\n");
      const worst = data.worst_scenario && typeof data.worst_scenario === "object"
        ? `${escapeHtml(data.worst_scenario.name || "")} (${fmtNum(data.worst_scenario.estimated_portfolio_loss_pct, 1, true)}%)`
        : "";
      return [
        fl ? `${t("agentOutput.risk.factorLoadings")} ${fl}${moreSpan(flEntries.length)}` : "",
        frc ? `${t("agentOutput.risk.riskContribution")} ${frc}${moreSpan(frcEntries.length)}` : "",
        mrt ? `${t("agentOutput.risk.marginalRiskTicker")} ${mrt}${moreSpan(mrtEntries.length)}` : "",
        (frc || mrt) ? `<span class="muted-text">${escapeHtml(t("agentOutput.risk.cashAwareNote"))}</span>` : "",
        tr ? `${t("agentOutput.risk.topRisks")} ${tr}${moreSpan(trList.length)}` : "",
        worst ? `${t("agentOutput.risk.worstScenario")} ${worst}` : "",
        scen ? `${t("agentOutput.risk.scenarios")}\n${scen}${moreSpan(scenList.length, "\n  ")}` : "",
        conc ? `${t("agentOutput.risk.concentration")} ${conc}${moreSpan(concList.length)}` : "",
        data.summary ? `${t("agentOutput.risk.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "regime": {
      const data = Array.isArray(out.regime_results) ? out.regime_results[0] : out;
      const mdList = data.mismatch_drivers || [];
      const md = mdList.slice(0, ITEM_CAP).map(m => "  • " + escapeHtml(m)).join("\n");
      const sv = data.state_vector && typeof data.state_vector === "object"
        ? `${escapeHtml(t("agentOutput.regime.stateVector.inflation"))} ${escapeHtml(stateValueLabel(data.state_vector.inflation_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.rates"))} ${escapeHtml(stateValueLabel(data.state_vector.rates_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.growth"))} ${escapeHtml(stateValueLabel(data.state_vector.growth_trend))} · ${escapeHtml(t("agentOutput.regime.stateVector.liquidity"))} ${escapeHtml(stateValueLabel(data.state_vector.liquidity))} · ${escapeHtml(t("agentOutput.regime.stateVector.volatility"))} ${escapeHtml(stateValueLabel(data.state_vector.volatility))}`
        : "";
      const hist = data.historical_outcome && typeof data.historical_outcome === "object"
        ? (data.historical_outcome.runner_available === false
          ? `<span class="muted-text">${escapeHtml(t("agentOutput.regime.historicalRunnerOff"))}</span>`
          : `${escapeHtml(t("agentOutput.regime.historicalAnalogs"))} ${escapeHtml(data.historical_outcome.message || "")}`)
        : "";
      return [
        `${t("agentOutput.regime.regime")} <b>${escapeHtml(data.current_regime)}</b>`,
        sv ? `${t("agentOutput.regime.state")} ${sv}` : "",
        hist,
        md ? `${t("agentOutput.regime.mismatchDrivers")}\n${md}${moreSpan(mdList.length, "\n  ")}` : "",
        data.summary ? `${t("agentOutput.regime.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "theme": {
      const data = Array.isArray(out.theme_results) ? out.theme_results[0] : out;
      const assessList = data.theme_assessments || [];
      const assessments = assessList.slice(0, ITEM_CAP).map(item => {
        const ev = (item.key_evidence && item.key_evidence[0]) ? String(item.key_evidence[0]).slice(0, 80) : "";
        const assessment = item.assessment ? ` — ${escapeHtml(item.assessment)}` : "";
        return `  ${escapeHtml(item.theme)}${assessment}${ev ? " · " + escapeHtml(ev) : ""}`;
      }).join("\n");
      const domList = (data.synthesis && data.synthesis.dominant_themes) || [];
      const dom = domList.slice(0, ITEM_CAP).map(escapeHtml).join(" · ");
      const bet = (data.implicit_portfolio_bet || "").trim();
      const crowdList = data.crowding_risks || [];
      const crowd = crowdList.slice(0, ITEM_CAP).map(escapeHtml).join("; ");
      return [
        bet ? `${t("agentOutput.theme.implicitBet")} ${escapeHtml(bet.length > 200 ? bet.slice(0, 200) + "…" : bet)}` : "",
        dom ? `${t("agentOutput.theme.dominant")} ${dom}${moreSpan(domList.length)}` : "",
        assessments ? `${assessments}${moreSpan(assessList.length, "\n  ")}` : "",
        crowd ? `${t("agentOutput.theme.crowding")} ${crowd}${moreSpan(crowdList.length)}` : "",
        data.summary ? `${t("agentOutput.theme.summary")} ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "validation": {
      const data = out.validation_review || out;
      const critList = data.critical_issues || [];
      const crit = critList.slice(0, ITEM_CAP)
        .map(i => `  [${escapeHtml(severityLabel((i.severity || "").toLowerCase()))}] ${escapeHtml(i.issue)}`)
        .join("\n");
      const brList = data.thesis_breaks || [];
      const br = brList.slice(0, ITEM_CAP).map(tb => "  !! " + escapeHtml(tb)).join("\n");
      return [
        crit ? `${crit}${moreSpan(critList.length, "\n  ")}` : "",
        br ? `${t("agentOutput.validation.thesisBreaks")}\n${br}${moreSpan(brList.length, "\n  ")}` : "",
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
          for (const q of pq.slice(0, ITEM_CAP)) {
            lines.push(`  <span class="mono">•</span> ${escapeHtml(q.length > 200 ? `${q.slice(0, 200)}…` : q)}`);
          }
          if (pq.length > ITEM_CAP) lines.push(`  ${moreSpan(pq.length).trimStart()}`);
        }
        const goals = nf.position_goals || [];
        if (goals.length) {
          lines.push(`<b>${escapeHtml(t("agentOutput.planner.positionGoals"))}</b>`);
          for (const g of goals.slice(0, ITEM_CAP)) {
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
          if (goals.length > ITEM_CAP) lines.push(`  ${moreSpan(goals.length).trimStart()}`);
        }
        if (lines.length) sections.push(`<b>${escapeHtml(t("agentOutput.planner.searchPlan"))}</b>\n${lines.join("\n")}`);
      }
      return sections.length ? sections.join("<br><br>") : `<em>${escapeHtml(t("agentOutput.planner.noOutputYet"))}</em>`;
    }
    case "manager": {
      const data = out.manager_review || out.planner_review || out;
      const actsList = data.actions || [];
      const acts = actsList.slice(0, ITEM_CAP)
        .map(a =>
          `  [${escapeHtml(priorityLabel(a.priority))}] ${escapeHtml(actionTypeLabel(a.action_type))} ${escapeHtml(actionScopeLabel(normalizeActionScope(a)))} · ${escapeHtml(a.position)}`
        )
        .join("\n");
      const es = data.executive_summary ? escapeHtml(data.executive_summary.slice(0, 200)) : "";
      return [
        acts ? `${acts}${moreSpan(actsList.length, "\n  ")}` : "",
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
      feedbackRounds: Array.isArray(bundle.feedbackRounds) ? bundle.feedbackRounds : (Array.isArray(bundle.feedback_rounds) ? bundle.feedback_rounds : []),
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
    feedbackRounds: Array.isArray(bundle.feedbackRounds) ? bundle.feedbackRounds : (Array.isArray(bundle.feedback_rounds) ? bundle.feedback_rounds : []),
  };
}

function compactAgentOutputsForStorage(outputs) {
  if (!outputs || typeof outputs !== "object") return {};
  return JSON.parse(JSON.stringify(outputs));
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

async function fetchReviewSummaries(limit = MAX_REVIEW_HISTORY) {
  try {
    const res = await fetch(`/api/reviews?limit=${encodeURIComponent(String(limit))}`);
    if (!res.ok) throw new Error(`reviews ${res.status}`);
    const data = await res.json();
    return Array.isArray(data.reviews) ? data.reviews : [];
  } catch {
    return null;
  }
}

function bundleFromReviewSummary(summary) {
  if (!summary || typeof summary !== "object") return null;
  return {
    reviewId: summary.review_id || summary.reviewId || "",
    savedAt: summary.saved_at || summary.savedAt || "",
    portfolioName: summary.portfolio_name || summary.portfolioName || "",
    requestedLocale: summary.requested_locale || summary.requestedLocale || "en",
    contentLocale: summary.content_locale || summary.contentLocale || summary.requested_locale || "en",
    translationFallbackUsed: Boolean(summary.translation_fallback_used || summary.translationFallbackUsed),
    manager: {
      executive_summary: summary.preview || "",
      do_nothing_case: "",
      actions: [],
    },
    validation: null,
    agentOutputs: {},
    agentOutputUpdatedAt: {},
    stepLogs: {},
    feedbackRounds: [],
  };
}

function managerFromReviewResult(data, managerOutput = null) {
  return (
    managerOutput?.manager_review ||
    managerOutput?.planner_review ||
    data?.final_state?.manager_review ||
    data?.agent_outputs?.manager?.manager_review ||
    data?.agent_outputs?.manager?.planner_review ||
    data?.agent_outputs?.manager ||
    managerOutput
  );
}

function bundleFromReviewResult(data, managerOutput = null) {
  const manager = managerFromReviewResult(data, managerOutput);
  return normalizeReviewBundle({
    reviewId: data.review_id || data.reviewId || "",
    savedAt: data.saved_at || data.savedAt || new Date().toISOString(),
    portfolioName: data.portfolio_name || data.portfolioName || document.getElementById("p-name")?.value?.trim() || "",
    requestedLocale: data.requested_locale || getLocale(),
    contentLocale: data.content_locale || data.requested_locale || getLocale(),
    translationFallbackUsed: Boolean(data.translation_fallback_used),
    manager,
    validation: data.final_state?.validation_review ?? null,
    agentOutputs: data.agent_outputs || {},
    agentOutputUpdatedAt: data.agent_output_updated_at || {},
    stepLogs: {},
    feedbackRounds: Array.isArray(data.feedback_rounds) ? data.feedback_rounds : [],
  });
}

async function initSavedReview() {
  try {
    const summaries = await fetchReviewSummaries(1);
    const bundle = summaries?.length ? bundleFromReviewSummary(summaries[0]) : loadReviewHistory()[0];
    if (!managerFromReviewBundle(bundle)) return;
    refreshSavedReviewSidebar(bundle);
  } catch {
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

function emptyAnalysisHtml() {
  return `<p class="evidence-empty">${escapeHtml(t("agentAnalysis.empty"))}</p>`;
}

function pendingAnalysisHtml() {
  return `<p class="evidence-empty evidence-pending">${escapeHtml(t("agentAnalysis.searching"))}</p>`;
}

function newsResearchPending() {
  return currentGlobalStatusState === "running" || currentGlobalStatusState === "waiting";
}

function cleanTextList(items) {
  return (Array.isArray(items) ? items : []).map((item) => String(item || "").trim()).filter(Boolean);
}

function listHtml(items) {
  const clean = cleanTextList(items);
  if (!clean.length) return emptyAnalysisHtml();
  return `<ul class="analysis-list">${clean.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function cappedListHtml(items, cap = 3) {
  const clean = cleanTextList(items);
  if (!clean.length) return emptyAnalysisHtml();
  const visible = clean.slice(0, cap);
  const more = clean.length > cap ? `<li class="muted-text">${escapeHtml(t("agentOutput.andMore", { count: clean.length - cap }))}</li>` : "";
  return `<ul class="analysis-list">${visible.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}${more}</ul>`;
}

function pillRowHtml(items) {
  const clean = cleanTextList(items);
  if (!clean.length) return emptyAnalysisHtml();
  return `<div class="analysis-chip-row">${clean.map((item) => `<span class="analysis-pill">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function kvHtml(rows) {
  const clean = rows.filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "");
  if (!clean.length) return emptyAnalysisHtml();
  return `<dl class="analysis-kv">${clean.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}</dl>`;
}

function meaningfulThemeDriftNote(value) {
  const text = value == null ? "" : String(value).trim();
  if (!text) return "";
  return /^(unknown|n\/a|not available|未知)\b/i.test(text) ? "" : text;
}

function labeledAnalysisBlock(label, html, className = "") {
  return `<div class="analysis-field-group${className ? ` ${className}` : ""}"><div class="analysis-field-label">${escapeHtml(label)}</div>${html}</div>`;
}

function themeAssessmentHtml(item) {
  const kind = String(item.narrative_kind || "").trim();
  const assets = cleanTextList(item.supporting_assets);
  const evidence = cleanTextList(item.key_evidence);
  return `
    <div class="analysis-item analysis-item--theme-assessment">
      <div class="theme-assessment-head">
        <span class="theme-assessment-title">${escapeHtml(item.theme)}</span>
        ${kind ? `<span class="analysis-pill analysis-pill--meta">${escapeHtml(kind)}</span>` : ""}
      </div>
      ${assets.length ? `<div class="theme-assessment-assets">${assets.map(escapeHtml).join(" · ")}</div>` : ""}
      <div class="theme-assessment-body">
        ${item.assessment ? `<p class="theme-assessment-assess">${escapeHtml(item.assessment)}</p>` : ""}
        ${item.implication ? `
          <p class="theme-assessment-impl">
            <span class="theme-assessment-lead">${escapeHtml(t("agentAnalysis.theme.implication"))}</span>
            ${escapeHtml(item.implication)}
          </p>
        ` : ""}
      </div>
      ${evidence.length ? `
        <details class="theme-assessment-evidence">
          <summary>${escapeHtml(t("agentAnalysis.theme.evidence"))} (${evidence.length})</summary>
          ${listHtml(evidence)}
        </details>
      ` : ""}
    </div>
  `;
}

function themePositionProfileHtml(item) {
  const sector = String(item.sector || "").trim();
  return `
    <div class="analysis-item">
      <div class="analysis-item-title">
        <span>${escapeHtml(item.ticker)}</span>
        ${sector ? `<span class="analysis-pill analysis-pill--meta">${escapeHtml(sector)}</span>` : ""}
      </div>
      ${item.business_model ? labeledAnalysisBlock(t("agentAnalysis.theme.businessModel"), `<p>${escapeHtml(item.business_model)}</p>`) : ""}
      ${labeledAnalysisBlock(t("agentAnalysis.theme.candidateThemes"), pillRowHtml(item.candidate_themes), "analysis-field-group--compact")}
      ${item.revenue_drivers ? labeledAnalysisBlock(t("agentAnalysis.theme.revenueDrivers"), `<p class="muted-text">${escapeHtml(item.revenue_drivers)}</p>`) : ""}
    </div>
  `;
}

function analogPeriodsHtml(periods) {
  const clean = Array.isArray(periods) ? periods : [];
  if (!clean.length) return emptyAnalysisHtml();
  return clean.map((item) => `
    <div class="analysis-item">
      <div class="analysis-item-title">
        <span>${escapeHtml(item.period || "")}</span>
        <span class="analysis-item-meta">${escapeHtml(item.match_score == null ? "" : `${t("results.analogMatchScore")} ${fmtNum(item.match_score, 2)}`)}</span>
      </div>
      ${kvHtml([
        [t("results.analogForwardWindow"), item.forward_window],
        [t("results.analogPortfolioReturn"), item.portfolio_return == null ? "" : fmtPctFromRatio(item.portfolio_return, 1)],
        [t("results.analogMaxDrawdown"), item.max_drawdown == null ? "" : fmtPctAbsFromRatio(item.max_drawdown, 1)],
      ])}
    </div>
  `).join("");
}

function metricBarsHtml(values, { percent = false, signed = false, maxItems = 10 } = {}) {
  const rows = sortedMetricEntries(values, { absolute: signed }).slice(0, maxItems);
  if (!rows.length) return emptyAnalysisHtml();
  const maxAbs = Math.max(...rows.map(([, value]) => Math.abs(value)), 0.0001);
  return rows.map(([name, value]) => {
    const width = Math.max(3, Math.min(100, Math.abs(value) / maxAbs * 100));
    const valueText = percent ? fmtPctFromRatio(value, 1) : fmtNum(value, 2, signed);
    return `
      <div class="evidence-bar-row">
        <div class="evidence-bar-meta"><span>${escapeHtml(name)}</span><strong>${escapeHtml(valueText)}</strong></div>
        <div class="evidence-bar-track"><span class="evidence-bar-fill${value < 0 ? " negative" : ""}" style="width: ${width}%"></span></div>
      </div>
    `;
  }).join("");
}

function scenarioLossBarsHtml(scenarios) {
  const rows = (Array.isArray(scenarios) ? scenarios : []).filter((item) => item && typeof item === "object");
  if (!rows.length) return emptyAnalysisHtml();
  const maxAbs = Math.max(...rows.map((item) => Math.abs(toFiniteNumber(item.estimated_portfolio_loss_pct) ?? 0)), 0.0001);
  return rows.map((item) => {
    const loss = toFiniteNumber(item.estimated_portfolio_loss_pct) ?? 0;
    const width = Math.max(3, Math.min(100, Math.abs(loss) / maxAbs * 100));
    return `
      <div class="analysis-item">
        <div class="evidence-bar-meta"><span>${escapeHtml(item.scenario || t("agentOutput.risk.scenarioFallback"))}</span><strong>${escapeHtml(fmtNum(loss, 1, true))}%</strong></div>
        <div class="evidence-bar-track"><span class="evidence-bar-fill${loss < 0 ? " negative" : ""}" style="width: ${width}%"></span></div>
      </div>
    `;
  }).join("");
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

function parseNewsConsideredItems(body) {
  return String(body || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("• "))
    .map((line) => {
      const source = line.slice(2).trim();
      const match = source.match(/^(?:\[(.*?)\]\s*)?(.+?)(?:\s+—\s+(https?:\/\/\S+))?$/);
      if (!match) return null;
      return {
        published: (match[1] || "").trim(),
        title: (match[2] || "").trim(),
        url: (match[3] || "").trim(),
      };
    })
    .filter((item) => item && item.title);
}

function newsConsideredHtml(run) {
  const items = parseNewsConsideredItems(run.body);
  if (!items.length) {
    return `<pre class="analysis-raw-block">${escapeHtml(truncateText(run.body, 1600))}</pre>`;
  }
  return `<ul class="analysis-news-links">${items.map((item) => {
    const title = escapeHtml(item.title);
    const published = `<span class="analysis-item-meta">${item.published ? escapeHtml(item.published) : "—"}</span>`;
    const link = item.url
      ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
      : `<span>${title}</span>`;
    return `<li>${published}${link}</li>`;
  }).join("")}</ul>`;
}

function normalizeNewsQueryKey(query) {
  return String(query || "").trim().toLowerCase();
}

function newsFocusFromView(view) {
  return view?.agentOutputs?.planner?.news_focus || view?.agentOutputs?.news?.news_focus || null;
}

function plannedNewsResearchSections(view, runs) {
  const focus = newsFocusFromView(view);
  if (!focus) return [{ title: "", items: runs.map((run) => ({ query: run.query, run })) }];

  const byQuery = new Map();
  for (const run of runs) {
    const key = normalizeNewsQueryKey(run.query);
    if (key && !byQuery.has(key)) byQuery.set(key, run);
  }

  const used = new Set();
  const plannedItem = (query, meta = "") => {
    const cleanQuery = String(query || "").trim();
    const key = normalizeNewsQueryKey(cleanQuery);
    if (key) used.add(key);
    return { query: cleanQuery, meta, run: byQuery.get(key) || null };
  };

  const plannerTopics = (focus.portfolio_search_queries || [])
    .map((query) => plannedItem(query))
    .filter((item) => item.query);
  const tickerSearches = (focus.position_goals || [])
    .map((goal) => plannedItem(goal?.latest_news_query, goal?.ticker || ""))
    .filter((item) => item.query);
  const otherSearches = runs
    .filter((run) => !used.has(normalizeNewsQueryKey(run.query)))
    .map((run) => ({ query: run.query, run }));

  return [
    plannerTopics.length ? { title: "", items: plannerTopics } : null,
    tickerSearches.length ? { title: t("agentAnalysis.news.tickerSearches"), items: tickerSearches } : null,
    otherSearches.length ? { title: t("agentAnalysis.news.otherSearches"), items: otherSearches } : null,
  ].filter(Boolean);
}

function newsResearchSectionsHtml(view, runs) {
  const pending = newsResearchPending();
  const sections = plannedNewsResearchSections(view, runs);
  const hasItems = sections.some((section) => section.items.length);
  if (!hasItems) return pending ? pendingAnalysisHtml() : emptyAnalysisHtml();
  const missingHtml = pending ? pendingAnalysisHtml() : emptyAnalysisHtml();
  return sections.map((section) => `
    <div class="analysis-subsection">
      ${section.title ? `<h5>${escapeHtml(section.title)}</h5>` : ""}
      ${section.items.map((item) => `
        <div class="analysis-item">
          <div class="analysis-item-title">
            <span>${escapeHtml(item.query)}</span>
            ${item.meta ? `<span class="analysis-item-meta">${escapeHtml(item.meta)}</span>` : ""}
          </div>
          ${item.run ? newsConsideredHtml(item.run) : missingHtml}
        </div>
      `).join("")}
    </div>
  `).join("");
}

function renderPlannerAnalysisTab(view) {
  const focus = view?.agentOutputs?.planner?.news_focus || {};
  return `
    <div class="analysis-section">
      <h4>${escapeHtml(t("agentAnalysis.planner.portfolioGoal"))}</h4>
      ${focus.portfolio_goal ? `<p>${escapeHtml(focus.portfolio_goal)}</p>` : emptyAnalysisHtml()}
    </div>
    <div class="analysis-section">
      <h4>${escapeHtml(t("agentAnalysis.planner.macroTopics"))}</h4>
      ${listHtml(focus.portfolio_search_queries)}
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
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.news.consideredResearch"))}</h4>${newsResearchSectionsHtml(view, queries)}</div>
      </div>
    </div>
  `;
}

function renderRiskAnalysisTab(view) {
  const risk = riskReviewFromAgentOutputs(view?.agentOutputs);
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.risk.overview"))}</h4>${risk ? kvHtml([
          [t("agentOutput.risk.worstScenario"), risk.worst_scenario ? `${risk.worst_scenario.name || ""} ${fmtNum(risk.worst_scenario.estimated_portfolio_loss_pct, 1, true)}%` : ""],
          [t("agentOutput.risk.summary"), risk.summary],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.riskContribution"))}</h4>${metricBarsHtml(risk?.factor_risk_contribution, { percent: true })}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.marginalRiskTicker"))}</h4>${metricBarsHtml(risk?.marginal_risk_by_ticker, { percent: true })}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.scenarios"))}</h4><p class="muted-text">${escapeHtml(t("agentOutput.risk.scenarioCashNote"))}</p>${scenarioLossBarsHtml(risk?.scenario_losses)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.topRisks"))}</h4>${listHtml(risk?.top_risks || [])}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.risk.concentration"))}</h4>${listHtml(risk?.concentration_issues || [])}</div>
      </div>
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
          [t("results.analogAvgReturn"), hist.avg_return == null ? "" : fmtPctFromRatio(hist.avg_return, 1)],
          [t("results.analogMaxDrawdown"), hist.max_drawdown == null ? "" : fmtPctAbsFromRatio(hist.max_drawdown, 1)],
          [t("results.analogWinRate"), hist.win_rate == null ? "" : fmtPctAbsFromRatio(hist.win_rate, 0)],
        ])}${analogPeriodsHtml(hist.top_similar_periods)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.regime.mismatchDrivers"))}</h4>${listHtml(regime?.mismatch_drivers || [])}</div>
      </div>
    </div>
  `;
}

function renderThemeAnalysisTab(view) {
  const theme = agentReviewFromView(view || {}, "theme", "theme_results");
  const synthesis = theme?.synthesis || {};
  const driftNote = meaningfulThemeDriftNote(synthesis.theme_drift_note);
  return `
    <div class="analysis-grid">
      <div class="analysis-main">
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.overview"))}</h4>${theme ? kvHtml([
          [t("agentOutput.theme.implicitBet"), theme.implicit_portfolio_bet],
          [t("agentOutput.theme.summary"), theme.summary],
          [t("agentAnalysis.theme.drift"), driftNote],
        ]) : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentOutput.theme.dominant"))}</h4>${pillRowHtml(synthesis.dominant_themes)}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.themeAssessments"))}</h4>${theme?.theme_assessments?.length ? theme.theme_assessments.map(themeAssessmentHtml).join("") : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.positionProfiles"))}</h4>${theme?.position_profiles?.length ? theme.position_profiles.map(themePositionProfileHtml).join("") : emptyAnalysisHtml()}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.crowdingMomentum"))}</h4>${listHtml([].concat(theme?.crowding_risks || [], theme?.momentum_conflicts || []))}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.redundantExposures"))}</h4>${listHtml(synthesis.redundant_expressions || [])}</div>
        <div class="analysis-section"><h4>${escapeHtml(t("agentAnalysis.theme.missingExposures"))}</h4>${listHtml(synthesis.missing_exposures || [])}</div>
      </div>
    </div>
  `;
}

function feedbackRoundsFromView(view) {
  const rounds = view?.bundle?.feedbackRounds || view?.bundle?.feedback_rounds || [];
  return Array.isArray(rounds) ? rounds : [];
}

function latestSuccessfulFeedbackRound(rounds) {
  return Array.from(rounds).reverse().find((round) => round?.status === "done" && round?.manager_review);
}

function feedbackActionPreviewHtml(manager, maxItems = 3) {
  const actions = sortedManagerActions(manager).slice(0, maxItems);
  if (!actions.length) return emptyAnalysisHtml();
  return `
    <ul class="feedback-action-list">
      ${actions.map((action) => `
        <li>
          <span class="feedback-action-main">
            <strong>${escapeHtml(actionTypeLabel(action.action_type))}</strong>
            <span>${escapeHtml(action.position || t("actionScope.portfolio"))}</span>
          </span>
          <span class="feedback-action-meta">${escapeHtml(priorityLabel(normalizePriority(action.priority)))}</span>
          ${action.rationale ? `<p>${escapeHtml(truncateText(action.rationale, 180))}</p>` : ""}
        </li>
      `).join("")}
    </ul>
  `;
}

function feedbackLatestSnapshotHtml(view, rounds) {
  const latest = latestSuccessfulFeedbackRound(rounds);
  const manager = latest?.manager_review || view?.manager || {};
  const verdict = manager?.portfolio_verdict || {};
  const actions = sortedManagerActions(manager);
  const topAction = actions[0];
  return `
    <div class="feedback-latest">
      <div class="feedback-latest-head">
        <h4>${escapeHtml(t("agentAnalysis.feedback.latestTitle"))}</h4>
        ${latest ? `<span class="analysis-pill analysis-pill--meta">${escapeHtml(t("agentAnalysis.feedback.updated"))}</span>` : ""}
      </div>
      ${manager?.executive_summary ? `
        <p class="feedback-latest-summary">${escapeHtml(manager.executive_summary)}</p>
      ` : emptyAnalysisHtml()}
      <dl class="feedback-snapshot-grid">
        <div>
          <dt>${escapeHtml(t("results.actionTiming"))}</dt>
          <dd>${escapeHtml(priorityLabel(normalizePriority(verdict.action_timing)))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(t("results.primaryRisk"))}</dt>
          <dd>${escapeHtml(verdict.primary_risk || "")}</dd>
        </div>
        <div>
          <dt>${escapeHtml(t("share.topAction"))}</dt>
          <dd>${escapeHtml(topAction ? formatActionLine(topAction) : t("share.noImmediateAction"))}</dd>
        </div>
        <div>
          <dt>${escapeHtml(t("agentAnalysis.feedback.actions"))}</dt>
          <dd>${escapeHtml(t("agentAnalysis.feedback.actionCount", { count: actions.length }))}</dd>
        </div>
      </dl>
    </div>
  `;
}

function feedbackRoundHtml(round, index) {
  const manager = round?.manager_review || {};
  const status = String(round?.status || "done");
  const statusKey = status === "error" ? "error" : status === "running" ? "runningStatus" : "complete";
  return `
    <div class="analysis-item feedback-round ${status === "error" ? "feedback-round--error" : ""}">
      <div class="feedback-round-head">
        <div>
          <span class="feedback-round-title">${escapeHtml(t("agentAnalysis.feedback.round", { count: index + 1 }))}</span>
          <span class="analysis-item-meta">${escapeHtml(formatSavedAt(round?.submitted_at || ""))}</span>
        </div>
        <span class="analysis-pill analysis-pill--meta">${escapeHtml(t(`agentAnalysis.feedback.${statusKey}`))}</span>
      </div>
      <div class="feedback-message feedback-message--user">
        <div class="feedback-speaker">${escapeHtml(t("agentAnalysis.feedback.you"))}</div>
        <p>${escapeHtml(round?.user_comment || "")}</p>
      </div>
      ${status === "error" ? `
        <div class="feedback-message feedback-message--manager">
          <div class="feedback-speaker">${escapeHtml(t("agentAnalysis.feedback.manager"))}</div>
          <p>${escapeHtml(round?.error || t("agentAnalysis.feedback.failed"))}</p>
        </div>
      ` : ""}
      ${manager.executive_summary ? `
        <div class="feedback-message feedback-message--manager">
          <div class="feedback-speaker">${escapeHtml(t("agentAnalysis.feedback.manager"))}</div>
          <p>${escapeHtml(manager.executive_summary)}</p>
        </div>
      ` : ""}
      ${manager.actions?.length ? `
        <div class="feedback-round-actions">
          <div class="analysis-field-label">${escapeHtml(t("agentAnalysis.feedback.topActions"))}</div>
          ${feedbackActionPreviewHtml(manager)}
        </div>
      ` : ""}
    </div>
  `;
}

function renderFeedbackAnalysisTab(view) {
  const rounds = feedbackRoundsFromView(view);
  const reviewId = view?.bundle?.reviewId || "";
  const disabled = feedbackRerunInFlight || !reviewId;
  return `
    <div class="feedback-layout">
      <div class="analysis-main">
        <div class="analysis-section">
          <h4>${escapeHtml(t("agentAnalysis.feedback.title"))}</h4>
          <form class="feedback-form" data-feedback-form>
            <label class="sr-only" for="feedback-comment">${escapeHtml(t("agentAnalysis.feedback.comment"))}</label>
            <textarea id="feedback-comment" class="feedback-textarea" rows="5" ${disabled ? "disabled" : ""} placeholder="${escapeHtml(t("agentAnalysis.feedback.placeholder"))}" data-i18n-placeholder="agentAnalysis.feedback.placeholder"></textarea>
            <div class="feedback-actions">
              <span class="feedback-status" data-feedback-status aria-live="polite">${feedbackRerunInFlight ? escapeHtml(t("agentAnalysis.feedback.running")) : ""}</span>
              <button type="submit" class="btn-primary" ${disabled ? "disabled" : ""}>${escapeHtml(feedbackRerunInFlight ? t("agentAnalysis.feedback.runningButton") : t("agentAnalysis.feedback.submit"))}</button>
            </div>
          </form>
        </div>
        <div class="analysis-section">
          <h4>${escapeHtml(t("agentAnalysis.feedback.history"))}</h4>
          ${rounds.length ? rounds.map(feedbackRoundHtml).join("") : emptyAnalysisHtml()}
        </div>
      </div>
      <aside class="feedback-side">
        ${feedbackLatestSnapshotHtml(view, rounds)}
      </aside>
    </div>
  `;
}

async function submitUserFeedback(comment) {
  const reviewId = currentResultsView?.bundle?.reviewId || "";
  if (!reviewId) {
    showToast(t("agentAnalysis.feedback.missingReview"), true);
    return;
  }
  feedbackRerunInFlight = true;
  renderAgentAnalysisTabs(currentResultsView);
  try {
    const res = await fetch(`/api/review/${encodeURIComponent(reviewId)}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `feedback ${res.status}`);
    applySnapshotAgentOutputs(data.agent_outputs, data.agent_output_updated_at);
    const bundle = bundleFromReviewResult(data);
    const manager = managerFromReviewBundle(bundle);
    if (!manager) throw new Error("missing manager review");
    restoreAnalysisTraceFromBundle(bundle);
    applyResultsFromData(manager, bundle.validation, bundle);
    persistReviewBundle(bundle);
    refreshSavedReviewSidebar(bundle);
    void renderHistoryList();
    const lastRound = feedbackRoundsFromView({ bundle }).at(-1);
    if (lastRound?.status === "error") {
      showToast(lastRound.error || t("agentAnalysis.feedback.failed"), true);
    } else {
      showToast(t("agentAnalysis.feedback.saved"));
    }
  } catch {
    showToast(t("agentAnalysis.feedback.failed"), true);
  } finally {
    feedbackRerunInFlight = false;
    renderAgentAnalysisTabs(currentResultsView);
  }
}

function renderAgentAnalysisTabs(view = currentResultsView) {
  if (!view) return;
  const renderers = {
    planner: renderPlannerAnalysisTab,
    news: renderNewsAnalysisTab,
    risk: renderRiskAnalysisTab,
    regime: renderRegimeAnalysisTab,
    theme: renderThemeAnalysisTab,
    feedback: renderFeedbackAnalysisTab,
  };
  Object.entries(renderers).forEach(([agent, renderer]) => {
    const panel = document.getElementById(`agent-panel-${agent}`);
    if (panel) panel.innerHTML = renderer(view);
  });
  switchAgentAnalysisTab(activeAgentAnalysisTab, { render: false });
}

function switchAgentAnalysisTab(agent, { render = true } = {}) {
  activeAgentAnalysisTab = ["planner", "news", "risk", "regime", "theme", "feedback"].includes(agent) ? agent : "planner";
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
  });
  document.getElementById("agent-analysis-panels")?.addEventListener("submit", (event) => {
    const form = event.target?.closest?.("[data-feedback-form]");
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector("#feedback-comment");
    const comment = input?.value?.trim() || "";
    if (!comment) {
      showToast(t("agentAnalysis.feedback.emptyComment"), true);
      return;
    }
    void submitUserFeedback(comment);
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

  const execEl = document.getElementById("exec-summary");
  execEl.textContent = manager?.executive_summary || "";

  const verdict = manager?.portfolio_verdict;
  const actions = sortedManagerActions(manager);
  const stanceEl = document.getElementById("portfolio-stance");
  if (stanceEl) {
    const hasDecisionSummary =
      Boolean(String(manager?.executive_summary || "").trim()) ||
      hasMeaningfulPortfolioVerdict(verdict) ||
      actions.length > 0;
    if (hasDecisionSummary) {
      stanceEl.classList.remove("hidden");
      const verdictData = verdict && typeof verdict === "object" ? verdict : {};
      setElementText("verdict-action-timing", priorityLabel(normalizePriority(verdictData.action_timing)));
      const horizon = document.getElementById("verdict-horizon");
      if (horizon) {
        const horizonText = [
          verdictData.investment_horizon,
          verdictData.horizon_detail,
        ].filter((item) => String(item || "").trim()).join(", ");
        horizon.textContent = horizonText;
        const horizonItem = document.getElementById("verdict-horizon-item");
        if (horizonItem) horizonItem.classList.toggle("hidden", !horizonText);
      }
      setElementText("stance-primary-risk", verdictData.primary_risk);
      setElementText("stance-recommended-posture", verdictData.recommended_posture);
      setElementText("stance-rationale", verdictData.rationale);
    } else {
      stanceEl.classList.add("hidden");
      setElementText("verdict-action-timing", "");
      setElementText("verdict-horizon", "");
      setElementText("stance-primary-risk", "");
      setElementText("stance-recommended-posture", "");
      setElementText("stance-rationale", "");
    }
  }

  setElementText(
    "overview-top-action",
    formatTopActionSummary(actions),
  );
  renderAgentAnalysisTabs(currentResultsView);
  renderActionsTable(actions);
  renderActionCards(actions);

  document.getElementById("do-nothing").textContent =
    manager?.do_nothing_case || "";
}

function showResultsModal({ returnToHistory = false } = {}) {
  const el = document.getElementById("results-modal");
  if (!el) return;
  returnToHistoryOnResultsClose = Boolean(returnToHistory);
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("results-modal-close")?.focus();
}

function hideResultsModal() {
  const el = document.getElementById("results-modal");
  if (!el) return;
  const shouldReturnToHistory = returnToHistoryOnResultsClose;
  returnToHistoryOnResultsClose = false;
  el.classList.add("hidden");
  hideAgentAnalysisModal({ preserveBodyOverflow: true });
  if (shouldReturnToHistory) {
    showHistoryModal();
    return;
  }
  const historyOpen = !document.getElementById("history-modal")?.classList.contains("hidden");
  const llmOpen = !document.getElementById("llm-config-modal")?.classList.contains("hidden");
  const analysisOpen = !document.getElementById("agent-analysis-modal")?.classList.contains("hidden");
  if (!historyOpen && !llmOpen && !analysisOpen) document.body.style.overflow = "";
}

function showAgentAnalysisModal() {
  const el = document.getElementById("agent-analysis-modal");
  if (!el) return;
  renderAgentAnalysisTabs(currentResultsView);
  el.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("agent-analysis-modal-close")?.focus();
}

function hideAgentAnalysisModal({ preserveBodyOverflow = false } = {}) {
  const el = document.getElementById("agent-analysis-modal");
  if (!el) return;
  el.classList.add("hidden");
  if (preserveBodyOverflow) return;
  const resultsOpen = !document.getElementById("results-modal")?.classList.contains("hidden");
  const historyOpen = !document.getElementById("history-modal")?.classList.contains("hidden");
  const llmOpen = !document.getElementById("llm-config-modal")?.classList.contains("hidden");
  if (!resultsOpen && !historyOpen && !llmOpen) document.body.style.overflow = "";
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
  const analysisOpen = !document.getElementById("agent-analysis-modal")?.classList.contains("hidden");
  if (!historyOpen && !resultsOpen && !analysisOpen) document.body.style.overflow = "";
}

async function openReviewById(reviewId, { returnToHistory = false } = {}) {
  const res = await fetch(`/api/review/${encodeURIComponent(reviewId)}/result`);
  if (!res.ok) throw new Error(`review ${res.status}`);
  const data = await res.json();
  const bundle = bundleFromReviewResult(data);
  const mgr = managerFromReviewBundle(bundle);
  if (!mgr) throw new Error("missing manager review");
  restoreAnalysisTraceFromBundle(bundle);
  applyResultsFromData(mgr, bundle.validation, bundle);
  showResultsModal({ returnToHistory });
}

async function openSavedReviewFromStorage() {
  try {
    const summaries = await fetchReviewSummaries(1);
    const bundle = summaries?.length ? bundleFromReviewSummary(summaries[0]) : loadReviewHistory()[0];
    if (!bundle) {
      showToast(t("history.noSavedReviewYet"), true);
      return;
    }
    if (bundle.reviewId && summaries?.length) {
      await openReviewById(bundle.reviewId);
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

async function renderHistoryList() {
  const ul = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  const count = document.getElementById("history-count");
  if (!ul) return;
  const summaries = await fetchReviewSummaries(MAX_REVIEW_HISTORY);
  const source = summaries?.length ? summaries.map(bundleFromReviewSummary).filter(Boolean) : loadReviewHistory();
  const list = source
    .map((bundle) => ({ bundle, mgr: managerFromReviewBundle(bundle) }))
    .filter((entry) => entry.mgr);
  ul.innerHTML = "";
  if (list.length === 0) {
    if (empty) empty.classList.remove("hidden");
    if (count) count.textContent = t("history.countEmpty");
    return;
  }
  if (empty) empty.classList.add("hidden");
  if (count) count.textContent = t("history.count", { count: list.length });
  for (const { bundle, mgr } of list) {
    const portfolioName = (bundle.portfolioName || "").trim() || t("common.portfolio");
    const savedAt = bundle.savedAt ? formatSavedAt(bundle.savedAt) : "";
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-row-btn";
    btn.setAttribute("aria-label", historyRowLabel(bundle));
    btn.innerHTML = `
      <span class="history-row-top">
        <span class="history-row-title">${escapeHtml(portfolioName)}</span>
        ${savedAt ? `<span class="history-row-time">${escapeHtml(savedAt)}</span>` : ""}
      </span>
      <span class="history-row-preview">${escapeHtml(
        truncateText(mgr.executive_summary || mgr.do_nothing_case || t("history.previewFallback"), 160),
      )}</span>
    `;
    btn.addEventListener("click", async () => {
      try {
        hideHistoryModal();
        if (summaries?.length && bundle.reviewId) {
          await openReviewById(bundle.reviewId, { returnToHistory: true });
          return;
        }
        restoreAnalysisTraceFromBundle(bundle);
        applyResultsFromData(mgr, bundle.validation, bundle.agentOutputs || _agentOutputs);
        currentResultsView = { ...(currentResultsView || {}), bundle };
        showResultsModal({ returnToHistory: true });
      } catch {
        showToast(t("history.savedReviewLoadError"), true);
      }
    });
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function showHistoryModal() {
  migrateLegacyReviewToHistory();
  void renderHistoryList();
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
  if (!document.getElementById("agent-analysis-modal")?.classList.contains("hidden")) {
    return;
  }
  if (!document.getElementById("llm-config-modal")?.classList.contains("hidden")) {
    return;
  }
  document.body.style.overflow = "";
}

async function renderResults(managerOutput, reviewId) {
  const res = await fetch(`/api/review/${reviewId}/result`);
  if (!res.ok) throw new Error(`review ${res.status}`);
  const data = await res.json();
  const {
    agent_outputs,
    agent_output_updated_at,
  } = data;
  applySnapshotAgentOutputs(agent_outputs, agent_output_updated_at);

  const bundle = bundleFromReviewResult(data, managerOutput);
  const manager = managerFromReviewBundle(bundle);
  const validation = bundle.validation;
  applyResultsFromData(manager, validation, agent_outputs || _agentOutputs);
  Object.assign(bundle, lastStartBody?.portfolio
    ? { portfolio: lastStartBody.portfolio }
    : { portfolio: buildPortfolio(), });
  bundle.agentOutputs = compactAgentOutputsForStorage(_agentOutputs);
  bundle.agentOutputUpdatedAt = Object.assign({}, currentAgentOutputUpdatedAt);
  bundle.stepLogs = compactStepLogsForStorage(agentStepHistory);
  applyResultsFromData(manager, validation, bundle);
  refreshSavedReviewSidebar(bundle);
  void renderHistoryList();
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

function agentElapsedSeconds(agent, nowMs = Date.now()) {
  const start = agentStartTimes[agent];
  if (!start) return 0;
  const end = agentEndTimes[agent] || nowMs;
  return Math.max(0, Math.floor((end - start) / 1000));
}

function renderAgentElapsed(agent) {
  const el = document.querySelector(`#card-${agent} .agent-elapsed`);
  if (!el || !agentStartTimes[agent]) return;
  el.textContent = fmtAgentRunTime(agentElapsedSeconds(agent));
}

function startElapsedTimer(agent) {
  clearInterval(agentTimerIds[agent]);
  agentStartTimes[agent] = Date.now();
  delete agentEndTimes[agent];
  renderAgentElapsed(agent);
  agentTimerIds[agent] = setInterval(() => {
    renderAgentElapsed(agent);
    refreshDrawer(agent);
  }, 1000);
}

function stopElapsedTimer(agent) {
  clearInterval(agentTimerIds[agent]);
  delete agentTimerIds[agent];
  agentEndTimes[agent] = Date.now();
  renderAgentElapsed(agent);
}

function renderCompactStep(agent, label, isActive) {
  const log = document.querySelector(`#card-${agent} .agent-stream-log`);
  const row = document.querySelector(`#card-${agent} .agent-stream-row`);
  if (!log || !row) return;
  row.classList.remove("hidden");
  row.classList.remove("agent-step-status-row");
  log.removeAttribute("id");
  log.querySelectorAll(".stream-entry.active").forEach(el => el.classList.remove("active"));
  const entry = document.createElement("div");
  entry.className = "stream-entry" + (isActive ? " active" : "");
  entry.textContent = label;
  log.replaceChildren(entry);
}

function clearStreamLog(agent) {
  const log = document.querySelector(`#card-${agent} .agent-stream-log`);
  const row = document.querySelector(`#card-${agent} .agent-stream-row`);
  if (log) log.innerHTML = "";
  if (log) log.removeAttribute("id");
  if (row) row.classList.add("hidden");
  if (row) row.classList.remove("agent-step-status-row");
}

function cardStateForAgent(agent) {
  const card = document.getElementById(`card-${agent}`);
  if (card?.classList.contains("running")) return "running";
  if (card?.classList.contains("done")) return "done";
  if (card?.classList.contains("error")) return "error";
  if (card?.classList.contains("waiting")) return "waiting";
  return "idle";
}

function stepStatusFor(agent, index) {
  const progress = agentStepProgress[agent] || { active: -1, done: new Set(), labels: {} };
  const cardState = cardStateForAgent(agent);
  if (progress.done.has(index) || cardState === "done") return "done";
  if (cardState === "error" && (progress.active === index || progress.active < 0)) return "error";
  if (progress.active === index) return "running";
  return "waiting";
}

function stepStatusIcon(status) {
  const icons = {
    done: "✓",
    running: "⟳",
    error: "!",
    waiting: "○",
  };
  return icons[status] || icons.waiting;
}

function stepStatusLabel(status) {
  const labels = {
    done: t("status.done"),
    running: t("status.running"),
    error: t("status.error"),
    waiting: t("status.waiting"),
  };
  return labels[status] || status;
}

function renderAgentStepStatus(agent) {
  const card = document.getElementById(`card-${agent}`);
  const log = card?.querySelector(".agent-stream-log");
  const row = card?.querySelector(".agent-stream-row");
  if (!card || !log || !row) return;
  const plan = getAgentPlan(agent);
  const progress = agentStepProgress[agent] || { active: -1, done: new Set(), labels: {} };
  row.classList.remove("hidden");
  row.classList.add("agent-step-status-row");
  log.id = `card-${agent}-steps`;
  log.innerHTML = plan.steps.map((step, index) => {
    const status = stepStatusFor(agent, index);
    const liveLabel = progress.labels?.[index];
    const subHtml = liveLabel ? `<span class="agent-step-sub">${escapeHtml(liveLabel)}</span>` : "";
    return `
      <div class="agent-step-status agent-step-status-${status}">
        <span class="agent-step-icon" aria-hidden="true">${escapeHtml(stepStatusIcon(status))}</span>
        <span class="agent-step-name">${escapeHtml(step)}</span>
        <span class="agent-step-state">${escapeHtml(stepStatusLabel(status))}</span>
        ${subHtml}
      </div>`;
  }).join("");
}

function isCompletedStepEvent(agent, stepIndex, label) {
  const text = String(label || "");
  // The news worker reports its final aggregate on the same step index as its active search.
  return agent === "news" && stepIndex === 2 && text.startsWith("Combined ");
}

function toggleAgentStepStatus(agent) {
  const card = document.getElementById(`card-${agent}`);
  const header = card?.querySelector(".card-header");
  if (!card || !header) return;
  const opening = !card.classList.contains("steps-open");
  card.classList.toggle("steps-open", opening);
  header.setAttribute("aria-expanded", opening ? "true" : "false");
  if (opening) {
    renderAgentStepStatus(agent);
    return;
  }
  const progress = agentStepProgress[agent];
  const label = progress?.active >= 0 ? progress.labels?.[progress.active] : "";
  if (label) renderCompactStep(agent, label, true);
  else clearStreamLog(agent);
}

function recordStep(agent, stepIndex, label) {
  if (!agentStepProgress[agent]) agentStepProgress[agent] = { active: -1, done: new Set(), labels: {} };
  const prev = agentStepProgress[agent].active;
  if (prev >= 0 && prev !== stepIndex) agentStepProgress[agent].done.add(prev);
  const completed = isCompletedStepEvent(agent, stepIndex, label);
  if (completed) agentStepProgress[agent].done.add(stepIndex);
  agentStepProgress[agent].active = completed ? -1 : stepIndex;
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
  if (document.getElementById(`card-${agent}`)?.classList.contains("steps-open")) {
    renderAgentStepStatus(agent);
  } else {
    renderCompactStep(agent, label, !completed);
  }
}

function completeAllSteps(agent) {
  const state = agentStepProgress[agent];
  if (!state) return;
  const plan = getAgentPlan(agent);
  if (plan) {
    for (let i = 0; i < plan.steps.length; i++) state.done.add(i);
  }
  state.active = -1;
  if (document.getElementById(`card-${agent}`)?.classList.contains("steps-open")) {
    renderAgentStepStatus(agent);
  } else {
    clearStreamLog(agent);
  }
}

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

function requestNotifPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function sendCompletionNotification() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  if (document.hasFocus()) return;
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
  currentResultsView = null;
  returnToHistoryOnResultsClose = false;
  currentShareArtifact = null;
  for (const k of Object.keys(agentTimerIds)) { clearInterval(agentTimerIds[k]); delete agentTimerIds[k]; }
  for (const k of Object.keys(agentStartTimes)) delete agentStartTimes[k];
  for (const k of Object.keys(agentEndTimes)) delete agentEndTimes[k];
  for (const k of Object.keys(agentStepProgress)) delete agentStepProgress[k];
  for (const k of Object.keys(_agentOutputs)) delete _agentOutputs[k];
  for (const k of Object.keys(currentAgentOutputUpdatedAt)) delete currentAgentOutputUpdatedAt[k];
  for (const k of Object.keys(agentStepHistory)) delete agentStepHistory[k];
  _currentActiveAgent = null;
  clearReviewElapsedTimer();
  clearAgentSummaryQueue();

  document.querySelectorAll(".agent-card").forEach(card => {
    const agent = card.dataset.agent;
    const loaderClass = card.classList.contains("data-loader-panel") ? " data-loader-panel" : "";
    card.className = `agent-card${loaderClass}`;
    if (agent !== "data") {
      wireAgentCardInteractions(card, agent);
    }
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
  dataLoaderTickerStatus.clear();
  renderDataLoaderHistory();
  setDataLoaderExpanded(false);
  setDataLoaderStatus("idle", dataLoaderDetail("dataLoader.waitingToLoad"), false);
  setButtonBusy(document.getElementById("start-btn"), false);
  setStopButtonRunning(false);
}
