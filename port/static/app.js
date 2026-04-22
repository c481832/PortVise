// ── Default example positions (price filled from quote API) ─────────────────
const DEFAULT_POSITIONS = [
  { ticker: "NVDA", name: "Nvidia", weight: 12, quantity: 25, sector: "Technology", asset_class: "equity",
    entry_thesis: "AI compute monopoly, data center capex supercycle driven by LLM training demand" },
  { ticker: "MSFT", name: "Microsoft", weight: 10, quantity: 30, sector: "Technology", asset_class: "equity",
    entry_thesis: "Azure cloud + Copilot AI monetisation; recurring revenue model with pricing power" },
  { ticker: "TLT", name: "iShares 20Y Treasury", weight: 10, quantity: 200, sector: "Fixed Income", asset_class: "bond",
    entry_thesis: "Duration add at rate peak; Fed pivot trade for H1 2024" },
  { ticker: "XOM", name: "ExxonMobil", weight: 8, quantity: 80, sector: "Energy", asset_class: "equity",
    entry_thesis: "Energy transition underinvestment; strong FCF, buybacks, dividend growth" },
  { ticker: "JPM", name: "JPMorgan Chase", weight: 8, quantity: 45, sector: "Financials", asset_class: "equity",
    entry_thesis: "Best-in-class bank; benefits from higher-for-longer rates via NIM expansion" },
  { ticker: "ASML", name: "ASML Holding", weight: 7, quantity: 5, sector: "Technology", asset_class: "equity",
    entry_thesis: "EUV monopoly; only supplier of lithography tools enabling sub-5nm chips" },
];

let currentReviewId = null;
let eventSource = null;
let lastStartBody = null;

// ── Agent progress state ──────────────────────────────────────────────────
const agentStartTimes = {};
const agentEndTimes = {};
const agentTimerIds = {};
const agentStepProgress = {}; // agent -> { active: N, done: Set<N> }
let completedAgentCount = 0;
const AGENT_CARD_NAMES = new Set(["planner","news","risk","regime","theme","validation","manager"]);
/** Pipeline completions (planner ×2, news ×2, risk, regime, theme, validation, manager). */
const PIPELINE_DONE_TOTAL = 9;

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
  planner:    { label:"Planner",
    desc:"Same fast LLM runs twice: first it turns portfolio CONTEXT and theses into web search queries for news; after the news briefing it plans curated context for Risk, Regime, and Theme.",
    steps:["Plan news search queries", "Plan downstream context for parallel analysts"] },
  data:       { label:"Data",
    desc:"Fetches live prices, 1-day/1-month returns, and 52-week range for every position plus 9 macro indicators (GLD, USO, ^TNX, EEM, EFA, SPY, QQQ, XLF, ^VIX).",
    steps:["Fetch live prices & market indicators"] },
  news:       { label:"News",
    desc:"After the planner, web search tools run in parallel with live price fetches; when both finish, synthesis combines research with the market snapshot into the briefing.",
    steps:["Tool research (parallel with data)", "Synthesise with live prices"] },
  risk:       { label:"Risk",
    desc:"Python engine estimates factor loadings, marginal risk, stress scenarios, and clusters; the LLM turns that into ranked risks and fragilities.",
    steps:["Factor/stress engine + interpretation"] },
  regime:     { label:"Regime",
    desc:"Rule-based macro state vector from live indicators plus an LLM narrative on fit and mismatch, with forward analog outcomes when historical coverage is available.",
    steps:["Regime vector + conditional expectations"] },
  theme:      { label:"Theme",
    desc:"Infers implicit portfolio bets from holdings, scores themes vs raw news research, optional theme graph for overlapping narratives.",
    steps:["Seed themes · score vs news · synthesise"] },
  validation: { label:"Validation",
    desc:"Cross-checks risk, regime, and theme findings for internal contradictions, elevates thesis breaks, and assigns an overall consistency score.",
    steps:["Cross-check all agent findings for conflicts"] },
  manager:    { label:"Manager",
    desc:"Synthesises everything into a prioritised action plan — Reduce, Exit, Hedge, Rotate, Add or Monitor — with position-level sizing guidance.",
    steps:["Generate prioritised action plan"] },
};

// ── Plan modal state ──────────────────────────────────────────────────────
let _modalAgent = null;
let _drawerOpen = false;
let _drawerAgent = null;
let _drawerPinned = false;
let _autoFollowTimer = null;
const AUTO_FOLLOW_DELAY_MS = 3000;
const _agentOutputs = {};
const quoteTimers = new WeakMap();
const LAST_REVIEW_STORAGE_KEY = "portAdvisorLastReview";
const REVIEW_HISTORY_STORAGE_KEY = "portAdvisorReviewHistory";
const MAX_REVIEW_HISTORY = 30;
const TIMING_STORAGE_KEY = "portAdvisorAgentTimings";
const SIDEBAR_WIDTH_STORAGE_KEY = "portAdvisorSidebarWidth";
const SIDEBAR_MIN_PX = 180;
const SIDEBAR_MAX_PX = 560;
const LLM_STORAGE_KEY = "portAdvisorModelConfig";
const DATA_LOADER_ERROR_RE = /(missing portfolio history for analog matching|missing price history for holdings|yfinance returned no data for analog matching|insufficient historical windows for analog matching)/i;
const DATA_LOADER_HISTORY_MAX = 12;
const dataLoaderHistory = [];

/** LLM-using pipeline slots (data is tools-only / no LLM). */
const AGENT_MODEL_SLOTS = [
  { id: "planner", label: "Planner", hint: "fast endpoint (search + downstream context)" },
  { id: "news_tools", label: "News — tool loop", hint: "fast endpoint" },
  { id: "news_synthesis", label: "News — synthesis" },
  { id: "risk", label: "Risk" },
  { id: "regime", label: "Regime" },
  { id: "theme", label: "Theme" },
  { id: "validation", label: "Validation" },
  { id: "manager", label: "Manager" },
];

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

/** Primary / fast model dropdowns — explicit options only; selection is always a model id. */
function renderDefaultModelSelect(selectEl, modelOptions, serverDefaultName, savedOverride) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  const opts = Array.isArray(modelOptions) ? modelOptions : [];
  for (const m of opts) {
    const o = document.createElement("option");
    o.value = m;
    o.textContent = m;
    selectEl.appendChild(o);
  }
  const fallback = (serverDefaultName && String(serverDefaultName).trim()) || opts[0] || "";
  if (fallback) _ensureOption(selectEl, fallback);
  const pick =
    (savedOverride && String(savedOverride).trim()) || fallback;
  if (pick) {
    _ensureOption(selectEl, pick);
    selectEl.value = pick;
  }
}

function renderAgentModelSelects(modelOptions, defaultAgentModels, savedAgentModels) {
  const wrap = document.getElementById("llm-agent-model-rows");
  if (!wrap) return;
  wrap.innerHTML = "";
  const opts = Array.isArray(modelOptions) ? modelOptions : [];
  const saved = savedAgentModels && typeof savedAgentModels === "object" ? savedAgentModels : {};
  for (const slot of AGENT_MODEL_SLOTS) {
    const row = document.createElement("div");
    row.className = "cfg-field cfg-field--agent";

    const lab = document.createElement("label");
    lab.setAttribute("for", `cfg-agent-${slot.id}`);
    lab.appendChild(document.createTextNode(slot.label));
    if (slot.hint) {
      const sp = document.createElement("span");
      sp.className = "cfg-agent-hint";
      sp.textContent = ` (${slot.hint})`;
      lab.appendChild(sp);
    }

    const sel = document.createElement("select");
    sel.className = "cfg-select agent-model-select";
    sel.id = `cfg-agent-${slot.id}`;
    sel.dataset.agentKey = slot.id;

    for (const m of opts) {
      const o = document.createElement("option");
      o.value = m;
      o.textContent = m;
      sel.appendChild(o);
    }

    const def = (defaultAgentModels[slot.id] && String(defaultAgentModels[slot.id]).trim()) || "";
    if (def) _ensureOption(sel, def);
    const pick = (saved[slot.id] && String(saved[slot.id]).trim()) || def;
    if (pick) {
      _ensureOption(sel, pick);
      sel.value = pick;
    }

    row.appendChild(lab);
    row.appendChild(sel);
    wrap.appendChild(row);
    sel.addEventListener("change", scheduleSaveModelConfig);
  }
}

/** Non-empty fields only for URLs; models always sent when selects are populated. */
function buildLlmOptionalPayload() {
  const out = {};
  const u = _cfgVal("cfg-llm-base-url");
  const fu = _cfgVal("cfg-fast-llm-base-url");
  if (u) out.llm_base_url = u;
  if (fu) out.fast_llm_base_url = fu;

  const pm = _cfgVal("cfg-llm-model");
  const fm = _cfgVal("cfg-fast-llm-model");
  if (pm) out.llm_model = pm;
  if (fm) out.fast_llm_model = fm;

  const am = {};
  document.querySelectorAll("select.agent-model-select").forEach((sel) => {
    const k = sel.dataset.agentKey;
    const v = sel.value?.trim();
    if (k && v) am[k] = v;
  });
  if (Object.keys(am).length) out.agent_models = am;

  return Object.keys(out).length ? out : undefined;
}

let _llmSaveTimer = null;
function scheduleSaveModelConfig() {
  if (_llmSaveTimer) clearTimeout(_llmSaveTimer);
  _llmSaveTimer = setTimeout(() => {
    _llmSaveTimer = null;
    try {
      const j = buildLlmOptionalPayload();
      if (j) localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(j));
      else localStorage.removeItem(LLM_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, 400);
}

async function loadModelConfigUi() {
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
  const opts = Array.isArray(merged.model_options) ? merged.model_options : [];
  const defaults = merged.default_agent_models && typeof merged.default_agent_models === "object"
    ? merged.default_agent_models
    : {};

  renderDefaultModelSelect(
    document.getElementById("cfg-llm-model"),
    opts,
    server.llm_model,
    saved.llm_model
  );
  renderDefaultModelSelect(
    document.getElementById("cfg-fast-llm-model"),
    opts,
    server.fast_llm_model,
    saved.fast_llm_model
  );

  renderAgentModelSelects(opts, defaults, saved.agent_models);

  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el && v != null && v !== "") el.value = v;
  };
  set("cfg-llm-base-url", merged.llm_base_url);
  set("cfg-fast-llm-base-url", merged.fast_llm_base_url);

  if (!loadModelConfigUi._urlInputsWired) {
    loadModelConfigUi._urlInputsWired = true;
    for (const id of ["cfg-llm-base-url", "cfg-fast-llm-base-url"]) {
      document.getElementById(id)?.addEventListener("input", scheduleSaveModelConfig);
    }
    for (const id of ["cfg-llm-model", "cfg-fast-llm-model"]) {
      document.getElementById(id)?.addEventListener("change", scheduleSaveModelConfig);
    }
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

// ── Time estimation ──────────────────────────────────────────────────────
/** Pipeline agents in execution order for ETA calculation. */
const PIPELINE_ORDER = ["planner","news","risk","regime","theme","validation","manager"];
/** Default estimates (seconds) for agents with no history. */
const DEFAULT_AGENT_SECS = { planner:60, news:180, risk:180, regime:180, theme:180, validation:120, manager:120 };

let _reviewStartTime = null;
let _currentActiveAgent = null;

function loadTimingAverages() {
  try {
    const raw = localStorage.getItem(TIMING_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveAgentTiming(agent, durationSecs) {
  const avgs = loadTimingAverages();
  const prev = avgs[agent];
  // Exponential moving average (alpha=0.4) so recent runs weigh more
  avgs[agent] = prev ? Math.round(prev * 0.6 + durationSecs * 0.4) : Math.round(durationSecs);
  try { localStorage.setItem(TIMING_STORAGE_KEY, JSON.stringify(avgs)); } catch { /* ignore */ }
}

function estimateRemainingSecs() {
  const avgs = loadTimingAverages();
  let remaining = 0;
  for (const agent of PIPELINE_ORDER) {
    if (agentEndTimes[agent]) continue; // already done
    const est = avgs[agent] || DEFAULT_AGENT_SECS[agent] || 120;
    if (agentStartTimes[agent]) {
      // currently running — subtract elapsed
      const elapsed = (Date.now() - agentStartTimes[agent]) / 1000;
      remaining += Math.max(0, est - elapsed);
    } else {
      remaining += est;
    }
  }
  return Math.round(remaining);
}

function fmtDuration(totalSecs) {
  if (totalSecs < 60) return `${totalSecs}s`;
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function updatePipelineStatus() {
  const activeLabel = document.getElementById("pipeline-active-label");
  const etaEl = document.getElementById("pipeline-eta");
  if (!activeLabel || !etaEl) return;

  if (_currentActiveAgent) {
    const plan = AGENT_PLANS[_currentActiveAgent];
    activeLabel.textContent = (plan?.label || _currentActiveAgent) + " running";
  } else {
    activeLabel.textContent = "";
  }

  const remaining = estimateRemainingSecs();
  if (remaining > 0 && _currentActiveAgent) {
    etaEl.textContent = `~${fmtDuration(remaining)} remaining`;
  } else if (!_currentActiveAgent && completedAgentCount >= PIPELINE_DONE_TOTAL) {
    etaEl.textContent = "";
    activeLabel.textContent = "Complete";
    activeLabel.style.color = "var(--green)";
  } else {
    etaEl.textContent = "";
  }
}

function escapeHtml(s) {
  if (s == null || s === "") return "";
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

function showToast(message, isError = false, duration = 5200) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const t = document.createElement("div");
  t.className = `toast${isError ? " error" : ""}`;
  t.setAttribute("role", "alert");

  function fadeOutAndRemove() {
    t.style.opacity = "0";
    t.style.transition = "opacity 0.3s";
    setTimeout(() => t.remove(), 320);
  }

  if (isError) {
    const msgEl = document.createElement("span");
    msgEl.className = "toast-msg";
    msgEl.textContent = message;
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "toast-dismiss";
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", fadeOutAndRemove);
    t.appendChild(msgEl);
    t.appendChild(dismiss);
  } else {
    t.textContent = message;
    setTimeout(fadeOutAndRemove, duration);
  }

  document.body.appendChild(t);
}

function recordDataLoaderEvent(state, detail) {
  const text = String(detail || "").trim() || "Status updated.";
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
    list.innerHTML = "<li><span>--:--:--</span>No detailed events yet.</li>";
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
  if (label) label.textContent = expanded ? "Hide details" : "Show details";
  body.classList.toggle("hidden", !expanded);
  if (expanded) renderDataLoaderHistory();
}

function toggleDataLoaderExpanded() {
  const toggle = document.getElementById("data-loader-toggle");
  if (!toggle) return;
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  setDataLoaderExpanded(!expanded);
}

function setDataLoaderStatus(state, detail = "", allowRetry = false) {
  const badge = document.getElementById("data-loader-status");
  const detailEl = document.getElementById("data-loader-detail");
  const retryBtn = document.getElementById("retry-review-btn");
  const text = detail || "Historical market data status will appear here.";
  if (badge) {
    const labels = { idle: "Idle", running: "Running", done: "Done", error: "Error" };
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
  recordDataLoaderEvent(state, text);
}

function isDataLoaderError(message) {
  return DATA_LOADER_ERROR_RE.test(String(message || ""));
}

function formatDataLoaderError(message) {
  const text = String(message || "").trim();
  const analogMissing = text.match(/missing portfolio history for analog matching:\s*(.+)$/i);
  if (analogMissing) {
    return `Missing analog-matching history for: ${analogMissing[1]}.`;
  }
  const holdingsMissing = text.match(/missing price history for holdings:\s*(.+)$/i);
  if (holdingsMissing) {
    return `Missing holdings history for: ${holdingsMissing[1]}.`;
  }
  return text || "Historical data loader failed.";
}

function cloneReviewBody(body) {
  return JSON.parse(JSON.stringify(body));
}

async function retryLastReview() {
  if (!lastStartBody) {
    showToast("No previous review payload available to retry.", true);
    return;
  }
  await runReviewWithBody(cloneReviewBody(lastStartBody), { fromRetry: true });
}

function fmtUsd(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function fmtPrice(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

function fmtPctDisplay(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function toFiniteNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtNum(v, digits = 2, signed = false) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const sign = signed && n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}`;
}

function fmtPctFromRatio(v, digits = 1) {
  const n = toFiniteNumber(v);
  if (n == null) return "—";
  const pct = n * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

function pluralize(count, singular, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
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
    const res = await fetch(`/api/market/quote/${encodeURIComponent(ticker)}`);
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
    showToast("Add at least one position to refresh quotes.", true);
    return;
  }
  const hasTicker = wraps.some((w) => w.querySelector('[data-field="ticker"]')?.value?.trim());
  if (!hasTicker) {
    showToast("Enter at least one ticker to refresh.", true);
    return;
  }
  setButtonBusy(btn, true, "Refreshing market data");
  try {
    await Promise.all(wraps.map((w) => fetchQuoteForCard(w)));
    showToast("Market data refreshed from Yahoo Finance.");
  } finally {
    setButtonBusy(btn, false);
    refreshPositionsState();
  }
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
      meta.textContent = "No positions loaded";
    } else {
      const notesText = `${noteCount} ${pluralize(noteCount, "thesis note")}`;
      meta.textContent = `${total} ${pluralize(total, "position")} loaded · ${notesText}`;
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
    wEl.textContent = `${pct.toFixed(1)}%`;
    wEl.classList.toggle("muted", nav <= 0);
    sumW += pct;
  }

  const fmt = (n) => `${n.toFixed(1)}%`;
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

document.addEventListener("DOMContentLoaded", () => {
  const weightCol = document.querySelector(".positions-head-row span:nth-child(3)");
  if (weightCol) weightCol.textContent = "Weight %";

  DEFAULT_POSITIONS.forEach(addRow);
  updateWeightSummary();

  document.getElementById("add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("empty-add-position-btn")?.addEventListener("click", () => addRow());
  document.getElementById("restore-sample-btn")?.addEventListener("click", restoreDefaultPositions);
  document.getElementById("refresh-quotes-btn")?.addEventListener("click", () => refreshAllQuotes());
  document.getElementById("start-btn")?.addEventListener("click", startReview);
  document.getElementById("retry-review-btn")?.addEventListener("click", retryLastReview);
  document.getElementById("data-loader-toggle")?.addEventListener("click", toggleDataLoaderExpanded);
  document.getElementById("confirm-send-btn")?.addEventListener("click", sendConfirm);
  document.getElementById("open-saved-review")?.addEventListener("click", openSavedReviewFromStorage);
  document.getElementById("open-review-history")?.addEventListener("click", showHistoryModal);
  document.getElementById("open-llm-config")?.addEventListener("click", showLlmConfigModal);
  document.getElementById("llm-config-modal-close")?.addEventListener("click", hideLlmConfigModal);
  document.getElementById("llm-config-modal-backdrop")?.addEventListener("click", hideLlmConfigModal);
  document.getElementById("history-modal-close")?.addEventListener("click", hideHistoryModal);
  document.getElementById("history-modal-backdrop")?.addEventListener("click", hideHistoryModal);
  document.getElementById("results-modal-close")?.addEventListener("click", hideResultsModal);
  document.getElementById("results-modal-backdrop")?.addEventListener("click", hideResultsModal);
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

  document.getElementById("confirm-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendConfirm();
    }
  });

  document.querySelectorAll("#positions-body .position-row-wrap").forEach((wrap) => {
    fetchQuoteForCard(wrap);
  });
  setDataLoaderExpanded(false);
  setDataLoaderStatus("idle", "Historical market data status will appear here.", false);
});

function addRow(data = {}) {
  const grid = document.getElementById("positions-body");
  const wrap = document.createElement("div");
  wrap.className = "position-row-wrap";
  wrap.dataset.quoteState = "idle";

  const t = escapeHtml(data.ticker);
  const n = escapeHtml(data.name);
  const qty = data.quantity != null && data.quantity !== "" ? escapeHtml(String(data.quantity)) : "";
  const s = escapeHtml(data.sector);
  const thesis = escapeHtml(data.entry_thesis);
  const ac = data.asset_class || "equity";

  wrap.innerHTML = `
    <div class="position-row">
      <input type="text" data-field="ticker" class="pc-ticker" value="${t}" placeholder="SYM" autocomplete="off" title="Ticker" />
      <input type="text" data-field="name" value="${n}" placeholder="Name" title="Name" />
      <span data-ro="weight" class="row-metric muted" title="Weight % (computed automatically)">0.0%</span>
      <input type="text" data-field="sector" value="${s}" placeholder="Sector" title="Sector" />
      <select data-field="asset_class" title="Asset class">
        ${["equity", "bond", "commodity", "fx", "crypto"].map(a =>
          `<option${a === ac ? " selected" : ""}>${a}</option>`
        ).join("")}
      </select>
      <span data-ro="price" class="row-metric muted" title="Last fetched price">—</span>
      <input type="number" data-field="quantity" step="0.0001" value="${qty}" placeholder="0" title="Quantity" />
      <span data-ro="value" class="row-metric muted" title="Position value">—</span>
      <span data-ro="ret-1m" class="row-metric muted" title="1 month return">—</span>
      <span data-ro="ret-1y" class="row-metric muted" title="1 year return">—</span>
      <button type="button" class="btn-assert-toggle" aria-expanded="false" aria-label="Show or hide assertion" title="Assertion">▸</button>
      <button type="button" class="delete-btn" aria-label="Remove position">✕</button>
    </div>
    <div class="position-assertion-panel hidden">
      <div class="assertion-inner">
        <span class="assertion-label">Your assertion</span>
        <textarea data-field="entry_thesis" rows="3" placeholder="Why you own this position…">${thesis}</textarea>
      </div>
    </div>
  `;

  grid.appendChild(wrap);
  wirePositionRow(wrap);
  updateWeightSummary();
}

function restoreDefaultPositions() {
  const grid = document.getElementById("positions-body");
  if (!grid) return;
  grid.innerHTML = "";
  DEFAULT_POSITIONS.forEach(addRow);
  updateWeightSummary();
  document.querySelectorAll("#positions-body .position-row-wrap").forEach((wrap) => {
    fetchQuoteForCard(wrap);
  });
  showToast("Sample portfolio restored.");
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
  const portfolio = buildPortfolio();
  if (portfolio.positions.length === 0) {
    showToast("Add at least one position with a ticker.", true);
    return;
  }

  const startBody = { portfolio };
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
  setButtonBusy(startBtn, true, "Review running");
  hideResultsModal();
  document.getElementById("confirm-box").classList.add("hidden");
  setDataLoaderStatus(
    "running",
    fromRetry ? "Retrying review and reloading history…" : "Starting review and waiting for data loader…",
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
    showToast("Network error — could not start review.", true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setDataLoaderStatus("error", "Could not start review due to a network error.", true);
    return;
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* ignore */ }
    showToast(`Could not start review: ${detail}`, true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setDataLoaderStatus("error", `Could not start review: ${detail}`, true);
    return;
  }

  const data = await res.json();
  const review_id = data.review_id;
  if (!review_id) {
    showToast("Invalid response from server.", true);
    setGlobalStatus("error");
    setButtonBusy(startBtn, false);
    setDataLoaderStatus("error", "Server response did not include a review id.", true);
    return;
  }
  currentReviewId = review_id;
  setDataLoaderStatus("running", "Waiting for market data agent to finish…", false);
  subscribeSSE(review_id);
}

function subscribeSSE(reviewId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/review/${reviewId}/stream`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };

  eventSource.onerror = () => {
    eventSource.close();
    if (document.getElementById("global-status").textContent !== "Done") {
      setGlobalStatus("error");
      setButtonBusy(document.getElementById("start-btn"), false);
    }
  };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "agent_start":
      setCardState(msg.agent, "running");
      if (msg.agent === "data") {
        setDataLoaderStatus("running", "Loading historical and macro market data…", false);
      }
      agentStepProgress[msg.agent] = { active: -1, done: new Set(), labels: {} };
      _currentActiveAgent = msg.agent;
      startElapsedTimer(msg.agent);
      drawerAutoFollow(msg.agent);
      updatePipelineStatus();
      break;

    case "agent_step":
      recordStep(msg.agent, msg.step_index, msg.label);
      refreshDrawer(msg.agent);
      break;

    case "agent_done":
      stopElapsedTimer(msg.agent);
      completeAllSteps(msg.agent);
      clearStreamLog(msg.agent);
      setCardState(msg.agent, "done");
      // Save per-agent timing for future ETA estimation
      if (agentStartTimes[msg.agent] && agentEndTimes[msg.agent]) {
        saveAgentTiming(msg.agent, (agentEndTimes[msg.agent] - agentStartTimes[msg.agent]) / 1000);
      }
      if (msg.agent === "planner" && msg.output && typeof msg.output === "object") {
        renderCardOutput("planner", { ...(_agentOutputs.planner || {}), ...msg.output });
      } else if (msg.agent === "news" && msg.output && typeof msg.output === "object") {
        renderCardOutput("news", { ...(_agentOutputs.news || {}), ...msg.output });
      } else {
        renderCardOutput(msg.agent, msg.output);
      }
      if (msg.agent === "data") {
        setDataLoaderStatus("done", "Market data loaded successfully.", false);
      }
      refreshDrawer(msg.agent);
      if (AGENT_CARD_NAMES.has(msg.agent)) {
        completedAgentCount++;
        updatePipelineProgress();
      }
      _currentActiveAgent = null;
      updatePipelineStatus();
      drawerAutoFollowDelayed(msg.agent);
      if (msg.agent === "manager") {
        renderResults(msg.output, currentReviewId);
        setGlobalStatus("done");
        setButtonBusy(document.getElementById("start-btn"), false);
        sendCompletionNotification();
        if (eventSource) eventSource.close();
      }
      break;

    case "heartbeat":
      break;

    case "interrupt":
      setCardState("planner", "waiting");
      setGlobalStatus("waiting");
      showConfirmBox(msg.payload);
      break;

    case "error":
      setGlobalStatus("error");
      setButtonBusy(document.getElementById("start-btn"), false);
      console.error("[review error]", msg.message);
      showToast(msg.message || "Review failed.", true, 12000);
      if (isDataLoaderError(msg.message)) {
        setDataLoaderStatus("error", formatDataLoaderError(msg.message), true);
      } else {
        setDataLoaderStatus("error", String(msg.message || "Review failed."), false);
      }
      break;
  }
}

function showConfirmBox(payload) {
  const box = document.getElementById("confirm-box");
  const preview = payload?.portfolio_summary != null
    ? String(payload.portfolio_summary)
    : JSON.stringify(payload, null, 2);
  document.getElementById("confirm-preview").textContent = preview;
  document.getElementById("confirm-input").value = "";
  box.classList.remove("hidden");
  document.getElementById("confirm-input").focus();
}

async function sendConfirm() {
  const userResponse = document.getElementById("confirm-input").value.trim() || "ok";
  document.getElementById("confirm-box").classList.add("hidden");
  setCardState("planner", "done");
  setGlobalStatus("running");

  try {
    await fetch(`/api/review/${currentReviewId}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response: userResponse }),
    });
  } catch {
    showToast("Could not send confirmation.", true);
  }
}

const AGENT_STATUS_LABELS = {
  idle: "Idle",
  running: "Running",
  done: "Done",
  waiting: "Waiting",
  error: "Error",
};

function setCardState(agent, state) {
  const card = document.getElementById(`card-${agent}`);
  if (!card) return;
  card.className = `agent-card ${state}`;
  const label = card.querySelector(".agent-status-label");
  if (label) {
    label.textContent = AGENT_STATUS_LABELS[state] ?? state;
  }
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

function agentOutputHtml(agent, out) {
  if (!out) return "<em>No output</em>";

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
          `<b>Tool research (excerpt):</b> ${escapeHtml(s.slice(0, 480))}${s.length > 480 ? "…" : ""}`,
        );
      }
      const data = out.news_review;
      if (!data || typeof data !== "object") {
        return chunks.length ? chunks.join("<br><br>") : "<em>No briefing yet.</em>";
      }
      const macro = (data.macro_context || "").slice(0, 200);
      const themes = (data.market_themes || []).map(escapeHtml).join(" · ");
      const evts = (data.key_events || []).slice(0, 6).map(escapeHtml).join("; ");
      chunks.push(
        `<b>Macro:</b> ${escapeHtml(macro)}${macro.length >= 200 ? "…" : ""}`,
        themes ? `<b>Themes:</b> ${themes}` : "",
        evts ? `<b>Key events:</b> ${evts}` : "",
        data.summary ? `<b>Summary:</b> ${escapeHtml(data.summary)}` : "",
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
        .map((s) => `  • ${escapeHtml(s.scenario || "Scenario")}: ${fmtNum(s.estimated_portfolio_loss_pct, 1, true)}%`)
        .join("\n");
      return [
        `Risk score: ${chip(data.risk_score)}`,
        fl ? `Factor loadings: ${fl}` : "",
        frc ? `Risk contribution: ${frc}` : "",
        mrt ? `Marginal risk (ticker): ${mrt}` : "",
        tr ? `Top risks: ${tr}` : "",
        worst ? `Worst scenario: ${worst}` : "",
        scen ? `Scenarios:\n${scen}` : "",
        fr ? `Fragilities:\n${fr}` : "",
        conc ? `Concentration: ${conc}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "regime": {
      const data = Array.isArray(out.regime_results) ? out.regime_results[0] : out;
      const mm = (data.mismatches || []).map(m => "  • " + escapeHtml(m)).join("\n");
      const md = (data.mismatch_drivers || []).map(m => "  • " + escapeHtml(m)).join("\n");
      const sv = data.state_vector && typeof data.state_vector === "object"
        ? `infl ${escapeHtml(data.state_vector.inflation_trend)} · rates ${escapeHtml(data.state_vector.rates_trend)} · growth ${escapeHtml(data.state_vector.growth_trend)} · liq ${escapeHtml(data.state_vector.liquidity)} · vol ${escapeHtml(data.state_vector.volatility)}`
        : "";
      const hist = data.historical_outcome && typeof data.historical_outcome === "object"
        ? (data.historical_outcome.runner_available === false
          ? `<span class="muted-text">Historical runner: off</span>`
          : `Historical analogs: ${escapeHtml(data.historical_outcome.message || "")}`)
        : "";
      const fitNotes = (data.fit_notes || []).map(escapeHtml).join("; ");
      return [
        `Regime: <b>${escapeHtml(data.current_regime)}</b>`,
        sv ? `State: ${sv}` : "",
        `Fit: ${chip(data.portfolio_fit_score)} | Confidence: ${chip(data.regime_confidence)}`,
        fitNotes ? `Fit notes: ${fitNotes}` : "",
        hist,
        md ? `Mismatch drivers:\n${md}` : "",
        mm ? `Mismatches:\n${mm}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "theme": {
      const data = Array.isArray(out.theme_results) ? out.theme_results[0] : out;
      const scored = (data.scored_themes || []).slice(0, 5).map(st => {
        const ev = (st.key_evidence && st.key_evidence[0]) ? String(st.key_evidence[0]).slice(0, 80) : "";
        return `  ${escapeHtml(st.theme)} · exp ${fmtPctFromRatio(st.portfolio_exposure, 0)} · news ${fmtPctFromRatio(st.news_strength, 0)} · conf ${fmtPctFromRatio(st.confidence, 0)}${ev ? " — " + escapeHtml(ev) : ""}`;
      }).join("\n");
      const dom = (data.synthesis && data.synthesis.dominant_themes || []).slice(0, 4).map(escapeHtml).join(" · ");
      const bet = (data.implicit_portfolio_bet || "").trim();
      const crowd = (data.crowding_risks || []).map(escapeHtml).join("; ");
      return [
        `Alignment: ${chip(data.alignment_score)}`,
        bet ? `Implicit bet: ${escapeHtml(bet.length > 200 ? bet.slice(0, 200) + "…" : bet)}` : "",
        dom ? `Dominant: ${dom}` : "",
        scored || "",
        crowd ? `Crowding: ${crowd}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "validation": {
      const data = out.validation_review || out;
      const crit = (data.critical_issues || []).slice(0, 4)
        .map(i => `  [${escapeHtml((i.severity || "").toUpperCase())}] ${escapeHtml(i.issue)}`)
        .join("\n");
      const br = (data.thesis_breaks || []).map(t => "  !! " + escapeHtml(t)).join("\n");
      return [
        `Consistency: ${chip(data.confidence_score)}`,
        crit ? crit : "",
        br ? `Thesis breaks:\n${br}` : "",
        data.summary ? `Summary: ${escapeHtml(data.summary)}` : "",
      ].filter(Boolean).join("\n\n");
    }
    case "planner": {
      const sections = [];
      const nf = out.news_focus;
      if (nf) {
        const lines = [];
        const pg = nf.portfolio_goal || "";
        if (pg) lines.push(`<b>Portfolio goal:</b> ${escapeHtml(pg.length > 280 ? `${pg.slice(0, 280)}…` : pg)}`);
        const pq = nf.portfolio_search_queries || [];
        if (pq.length) {
          lines.push("<b>Planned macro topics (3):</b>");
          for (const q of pq.slice(0, 3)) {
            lines.push(`  <span class="mono">•</span> ${escapeHtml(q.length > 200 ? `${q.slice(0, 200)}…` : q)}`);
          }
        }
        const goals = nf.position_goals || [];
        if (goals.length) {
          lines.push("<b>Position goals and latest-news query:</b>");
          for (const g of goals.slice(0, 12)) {
            const t = escapeHtml(g.ticker || "");
            const gg = escapeHtml((g.goal || "").length > 160 ? `${(g.goal || "").slice(0, 160)}…` : (g.goal || ""));
            lines.push(`  <span class="mono">${t}</span> — ${gg || "—"}`);
            const lq = (g.latest_news_query || "").trim();
            if (lq) {
              lines.push(
                `    <span class="muted-text">→ latest news</span> ${escapeHtml(lq.length > 180 ? `${lq.slice(0, 180)}…` : lq)}`,
              );
            }
          }
          if (goals.length > 12) lines.push(`  <span class="muted-text">… +${goals.length - 12} more</span>`);
        }
        const macros = (nf.macro_indicator_tickers || []).filter(Boolean);
        if (macros.length) {
          lines.push(
            `<b>Macro indicators to fetch (parallel with news):</b> ${macros.map(escapeHtml).join(", ")}`,
          );
        }
        if (lines.length) sections.push(`<b>Phase 1 — search plan</b>\n${lines.join("\n")}`);
      }
      const dc = out.downstream_context;
      if (dc && typeof dc === "object") {
        const rationale = (dc.brief_rationale || "").trim();
        const rf = (dc.risk_focus || "").trim();
        const regf = (dc.regime_focus || "").trim();
        const tf = (dc.theme_focus || "").trim();
        const blocks = [];
        if (rationale) blocks.push(`<b>Rationale:</b> ${escapeHtml(rationale.length > 400 ? `${rationale.slice(0, 400)}…` : rationale)}`);
        if (rf) blocks.push(`<b>Risk focus:</b><br>${escapeHtml(rf.length > 1200 ? `${rf.slice(0, 1200)}…` : rf).replace(/\n/g, "<br>")}`);
        if (regf) blocks.push(`<b>Regime focus:</b><br>${escapeHtml(regf.length > 1200 ? `${regf.slice(0, 1200)}…` : regf).replace(/\n/g, "<br>")}`);
        if (tf) blocks.push(`<b>Theme focus:</b><br>${escapeHtml(tf.length > 1200 ? `${tf.slice(0, 1200)}…` : tf).replace(/\n/g, "<br>")}`);
        if (blocks.length) sections.push(`<b>Phase 2 — downstream context</b><br><br>${blocks.join("<br><br>")}`);
      }
      return sections.length ? sections.join("<br><br>") : "<em>No planner output yet.</em>";
    }
    case "manager": {
      const data = out.manager_review || out.planner_review || out;
      const acts = (data.actions || []).slice(0, 5)
        .map(a =>
          `  [${escapeHtml(a.priority)}] ${escapeHtml((a.action_type || "").toUpperCase())} ${escapeHtml(a.position)}`
        )
        .join("\n");
      const es = data.executive_summary ? escapeHtml(data.executive_summary.slice(0, 200)) : "";
      return [
        `Confidence: ${chip(data.overall_confidence)}`,
        acts || "",
        es ? `Summary: ${es}${(data.executive_summary || "").length > 200 ? "…" : ""}` : "",
      ].filter(Boolean).join("\n\n");
    }
    default:
      return `<pre>${escapeHtml(JSON.stringify(out, null, 2).slice(0, 400))}</pre>`;
  }
}

function formatSavedAt(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return "";
  }
}

function formatSavedReviewMeta(savedAt, reviewId) {
  const when = savedAt ? formatSavedAt(savedAt) : "";
  const idShort = reviewId ? String(reviewId).slice(0, 8) : "";
  const parts = [when];
  if (idShort) parts.push(`ID ${idShort}…`);
  return parts.filter(Boolean).join(" · ");
}

function migrateLegacyReviewToHistory() {
  try {
    if (localStorage.getItem(REVIEW_HISTORY_STORAGE_KEY)) return;
    const raw = localStorage.getItem(LAST_REVIEW_STORAGE_KEY);
    if (!raw) return;
    const bundle = JSON.parse(raw);
    if (!bundle?.manager && !bundle?.planner) return;
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
    return Array.isArray(arr) ? arr : [];
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
  meta.textContent = formatSavedReviewMeta(bundle.savedAt, bundle.reviewId);
}

function initSavedReview() {
  try {
    migrateLegacyReviewToHistory();
    const list = loadReviewHistory();
    const bundle = list[0];
    if (!bundle?.manager && !bundle?.planner) return;
    refreshSavedReviewSidebar(bundle);
  } catch {
    /* ignore */
  }
}

function applyResultsFromData(manager, validation) {
  const execEl = document.getElementById("exec-summary");
  execEl.textContent = manager?.executive_summary || "";

  const conf = toFiniteNumber(manager?.overall_confidence);
  const consistency = toFiniteNumber(validation?.confidence_score);
  document.getElementById("score-confidence").textContent =
    conf == null ? "—" : String(Math.round(conf));
  document.getElementById("score-consistency").textContent =
    consistency == null ? "—" : String(Math.round(consistency));

  const tbody = document.getElementById("actions-body");
  tbody.innerHTML = "";
  const priorityOrder = ["urgent", "this-week", "next-review", "watch"];
  const actions = [...(manager?.actions || [])];
  actions.sort((a, b) =>
    priorityOrder.indexOf(a.priority) - priorityOrder.indexOf(b.priority)
  );
  if (!actions.length) {
    const tr = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "actions-empty-cell";
    cell.textContent = "No position actions were returned. Check the do-nothing case or agent drawer for context.";
    tr.appendChild(cell);
    tbody.appendChild(tr);
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
      chip.className = `table-chip priority-chip priority-${a.priority}`;
      chip.textContent = a.priority ?? "—";
      cell.appendChild(chip);
      return cell;
    })());
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const chip = document.createElement("span");
      chip.className = `table-chip action-chip action-${a.action_type}`;
      chip.textContent = a.action_type ?? "—";
      cell.appendChild(chip);
      return cell;
    })());
    tr.appendChild((() => {
      const cell = document.createElement("td");
      const b = document.createElement("b");
      b.textContent = a.position ?? "—";
      cell.appendChild(b);
      return cell;
    })());
    tr.appendChild(td(null, a.rationale));
    tr.appendChild(td(null, a.size_guidance));
    tr.appendChild(td(null, a.hedge_instrument || "—"));
    tbody.appendChild(tr);
  }

  document.getElementById("do-nothing").textContent =
    manager?.do_nothing_case || "";
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
      showToast("No saved review yet.", true);
      return;
    }
    const mgr = bundle.manager || bundle.planner;
    if (!mgr) {
      showToast("Saved review is missing data.", true);
      return;
    }
    applyResultsFromData(mgr, bundle.validation);
    showResultsModal();
  } catch {
    showToast("Could not load saved review.", true);
  }
}

function historyRowLabel(bundle) {
  const name = (bundle.portfolioName || "").trim() || "Portfolio";
  const when = bundle.savedAt ? formatSavedAt(bundle.savedAt) : "";
  const idShort = bundle.reviewId ? String(bundle.reviewId).slice(0, 8) : "";
  const parts = [name];
  if (when) parts.push(when);
  if (idShort) parts.push(`${idShort}…`);
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
    const mgr = bundle.manager || bundle.planner;
    if (!mgr) continue;
    added += 1;
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-row-btn";
    btn.setAttribute("aria-label", historyRowLabel(bundle));
    btn.innerHTML = `
      <span class="history-row-top">
        <span class="history-row-title">${escapeHtml((bundle.portfolioName || "").trim() || "Portfolio")}</span>
        <span class="history-row-time">${escapeHtml(formatSavedReviewMeta(bundle.savedAt, bundle.reviewId))}</span>
      </span>
      <span class="history-row-preview">${escapeHtml(
        truncateText(mgr.executive_summary || mgr.do_nothing_case || "Open the saved decision memo.", 160),
      )}</span>
    `;
    btn.addEventListener("click", () => {
      applyResultsFromData(mgr, bundle.validation);
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
  const { final_state } = await res.json();

  const manager =
    managerOutput?.manager_review ||
    managerOutput?.planner_review ||
    managerOutput;
  const validation = final_state?.validation_review;

  applyResultsFromData(manager, validation);

  const bundle = {
    reviewId,
    savedAt: new Date().toISOString(),
    portfolioName: document.getElementById("p-name")?.value?.trim() || "",
    manager,
    validation: validation ?? null,
  };
  persistReviewBundle(bundle);
  refreshSavedReviewSidebar(bundle);
  showResultsModal();
}

// ── Elapsed timers ────────────────────────────────────────────────────────
function startElapsedTimer(agent) {
  agentStartTimes[agent] = Date.now();
  const el = document.querySelector(`#card-${agent} .agent-elapsed`);
  if (!el) return;
  agentTimerIds[agent] = setInterval(() => {
    el.textContent = Math.floor((Date.now() - agentStartTimes[agent]) / 1000) + "s";
    refreshDrawer(agent);
    updatePipelineStatus();
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

// ── Pipeline progress bar ─────────────────────────────────────────────────
function updatePipelineProgress() {
  const wrap = document.getElementById("pipeline-progress-wrap");
  const bar = document.getElementById("pipeline-progress-bar");
  const lbl = document.getElementById("pipeline-progress-label");
  if (!wrap) return;
  const total = PIPELINE_DONE_TOTAL;
  const pct = Math.round((completedAgentCount / total) * 100);
  wrap.style.display = "block";
  if (bar) bar.style.width = pct + "%";
  if (lbl) lbl.textContent = `${completedAgentCount} / ${total} steps done`;
}

// ── Step tracking ─────────────────────────────────────────────────────────
function recordStep(agent, stepIndex, label) {
  if (!agentStepProgress[agent]) agentStepProgress[agent] = { active: -1, done: new Set(), labels: {} };
  const prev = agentStepProgress[agent].active;
  if (prev >= 0 && prev !== stepIndex) agentStepProgress[agent].done.add(prev);
  agentStepProgress[agent].active = stepIndex;
  agentStepProgress[agent].labels[stepIndex] = label;
  appendStreamEntry(agent, label, true);
}

function completeAllSteps(agent) {
  const state = agentStepProgress[agent];
  if (!state) return;
  const plan = AGENT_PLANS[agent];
  if (plan) {
    for (let i = 0; i < plan.steps.length; i++) state.done.add(i);
  }
  state.active = -1;
}

// ── Agent drawer ─────────────────────────────────────────────────────────
function openDrawer(agent) {
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
    btn.setAttribute("aria-label", "Unpin (resume auto-follow)");
    btn.title = "Unpin (resume auto-follow)";
    const plan = AGENT_PLANS[_drawerAgent];
    bar.textContent = `Pinned to ${plan?.label || _drawerAgent}`;
    bar.classList.add("pinned-bar");
    if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  } else {
    btn.classList.remove("pinned");
    btn.setAttribute("aria-label", "Pin to this agent");
    btn.title = "Pin to this agent";
    bar.textContent = "Auto-following pipeline";
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
  const plan = AGENT_PLANS[agent];
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
  badgeEl.textContent = AGENT_STATUS_LABELS[cardState] ?? cardState;

  const timeEl = document.getElementById("drawer-agent-time");
  const start = agentStartTimes[agent];
  const end = agentEndTimes[agent];
  if (start && end) {
    timeEl.textContent = `${((end - start) / 1000).toFixed(1)}s`;
  } else if (start) {
    timeEl.textContent = `${Math.floor((Date.now() - start) / 1000)}s`;
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
  if (_agentOutputs[agent]) {
    outputEl.innerHTML = `<div class="drawer-output-heading">Output</div><pre>${agentOutputHtml(agent, _agentOutputs[agent])}</pre>`;
  } else {
    outputEl.innerHTML = "";
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
    ? `Review completed in ${elapsed}. Click to view results.`
    : "Review completed. Click to view results.";
  const n = new Notification("Portfolio Advisor", { body });
  n.onclick = () => { window.focus(); n.close(); };
}

function setGlobalStatus(state) {
  const el = document.getElementById("global-status");
  el.className = `badge badge-${state}`;
  const labels = { idle: "Idle", running: "Running", waiting: "Waiting", done: "Done", error: "Error" };
  el.textContent = labels[state] || state;
}

function resetCards() {
  // Stop all timers and clear progress state
  for (const k of Object.keys(agentTimerIds)) { clearInterval(agentTimerIds[k]); delete agentTimerIds[k]; }
  for (const k of Object.keys(agentStartTimes)) delete agentStartTimes[k];
  for (const k of Object.keys(agentEndTimes)) delete agentEndTimes[k];
  for (const k of Object.keys(agentStepProgress)) delete agentStepProgress[k];
  for (const k of Object.keys(_agentOutputs)) delete _agentOutputs[k];
  completedAgentCount = 0;
  _currentActiveAgent = null;
  _reviewStartTime = Date.now();

  // Reset pipeline status strip
  const activeLabel = document.getElementById("pipeline-active-label");
  const etaEl = document.getElementById("pipeline-eta");
  if (activeLabel) { activeLabel.textContent = "Starting"; activeLabel.style.color = ""; }
  if (etaEl) etaEl.textContent = "";

  // Reset pipeline progress bar
  const progressWrap = document.getElementById("pipeline-progress-wrap");
  const progressBar = document.getElementById("pipeline-progress-bar");
  if (progressWrap) progressWrap.style.display = "none";
  if (progressBar) progressBar.style.width = "0%";

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
    if (label) label.textContent = "Idle";
    const elapsed = card.querySelector(".agent-elapsed");
    if (elapsed) elapsed.textContent = "";
    clearStreamLog(agent);
  });

  _drawerPinned = false;
  if (_autoFollowTimer) { clearTimeout(_autoFollowTimer); _autoFollowTimer = null; }
  const pinBtn = document.getElementById("drawer-pin-btn");
  if (pinBtn) { pinBtn.classList.remove("pinned"); }
  const followBar = document.getElementById("drawer-follow-bar");
  if (followBar) { followBar.textContent = "Auto-following pipeline"; followBar.classList.remove("pinned-bar"); }
  dataLoaderHistory.length = 0;
  renderDataLoaderHistory();
  setDataLoaderExpanded(false);
  setDataLoaderStatus("idle", "Waiting to load historical market data.", false);
  setButtonBusy(document.getElementById("start-btn"), false);
}
