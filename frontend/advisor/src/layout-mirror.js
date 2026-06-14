
import { onLocaleChange, t } from "./i18n.js";

// Keep the compact ribbon and metadata chips synchronized with the canonical form and cards.
const AGENTS = ["data", "planner", "news", "risk", "regime", "theme", "validation", "manager"];
const STATES = ["running", "done", "error", "waiting"];

function classState(el) {
  if (!el) return "";
  for (const s of STATES) {
    if (el.classList.contains(s)) return s;
  }
  return "";
}

function ribbonTimeFor(state, elapsedText) {
  const elapsed = String(elapsedText || "").trim();
  if (elapsed) return elapsed;
  if (state === "done") return t("ribbon.done");
  if (state === "running") return t("ribbon.running");
  if (state === "waiting") return t("ribbon.waiting");
  if (state === "error") return t("ribbon.errored");
  return t("ribbon.idle");
}

function syncRibbonFromCard(agent) {
  const card = document.getElementById(`card-${agent}`);
  const node = document.querySelector(`.ribbon-node[data-agent="${agent}"]`);
  if (!card || !node) return;

  const state = classState(card);
  node.classList.remove(...STATES);
  if (state) node.classList.add(state);

  const cardElapsed = card.querySelector(".agent-elapsed")?.textContent || "";
  const nodeTime = node.querySelector(".node-time");
  if (nodeTime) nodeTime.textContent = ribbonTimeFor(state, cardElapsed);
}

function updateRibbonProgress() {
  const total = AGENTS.length;
  let done = 0;
  let running = 0;
  let error = 0;
  for (const agent of AGENTS) {
    const card = document.getElementById(`card-${agent}`);
    if (!card) continue;
    const s = classState(card);
    if (s === "done") done++;
    else if (s === "running" || s === "waiting") running++;
    else if (s === "error") error++;
  }
  const fill = document.getElementById("ribbon-progress-fill");
  const text = document.getElementById("ribbon-progress-text");
  const eta = document.getElementById("ribbon-progress-eta");
  const reviewDone = document.getElementById("global-status")?.classList.contains("badge-done");
  const pct = total ? (done / total) * 100 : 0;
  if (fill) fill.style.width = `${pct}%`;
  if (text) text.textContent = `${done} / ${total}`;
  if (eta) {
    if (error > 0) eta.textContent = t("ribbon.etaError");
    else if (reviewDone && done === total) eta.textContent = t("ribbon.etaComplete");
    else if (running > 0) eta.textContent = t("ribbon.etaRunning");
    else if (done === total && total > 0) eta.textContent = t("ribbon.etaComplete");
    else eta.textContent = "";
  }
  return { done, running, error, total };
}

function syncAllRibbon() {
  for (const agent of AGENTS) syncRibbonFromCard(agent);
  updateRibbonProgress();
}

function syncCrumbs() {
  const map = [
    ["p-name", "crumb-name"],
    ["p-benchmark", "crumb-benchmark"],
    ["p-date", "crumb-date"],
  ];
  for (const [inputId, crumbId] of map) {
    const input = document.getElementById(inputId);
    const out = document.getElementById(crumbId);
    if (!input || !out) continue;
    const v = String(input.value || "").trim();
    out.textContent = v || "—";
  }
}

function syncMetaChips() {
  const rows = document.querySelectorAll("#positions-body .position-row-wrap");
  const positions = rows.length;
  let notes = 0;
  for (const row of rows) {
    const t = row.querySelector('[data-field="entry_thesis"]')?.value?.trim();
    if (t) notes++;
  }
  const invested = document.getElementById("weight-positions")?.textContent || "—";

  const setText = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  };
  setText("meta-invested", invested);
  setText("meta-positions", String(positions));
  setText("meta-notes", String(notes));
}

function syncBriefSubs() {
  const positionsEl = document.getElementById("weight-positions");
  const sub = document.getElementById("weight-positions-sub");
  if (sub && positionsEl) {
    const rows = document.querySelectorAll("#positions-body .position-row-wrap").length;
    const nextText = rows
      ? t("summary.positionsSubCount", { count: rows })
      : t("summary.positionsSub");
    if (sub.textContent !== nextText) sub.textContent = nextText;
  }
}

function wireControls() {
  document.querySelectorAll(".ribbon-node").forEach((node) => {
    node.addEventListener("click", () => {
      const agent = node.dataset.agent;
      const card = agent ? document.getElementById(`card-${agent}`) : null;
      if (card) card.click();
    });
  });

}

function startObservers() {
  for (const agent of AGENTS) {
    const card = document.getElementById(`card-${agent}`);
    if (!card) continue;
    const obs = new MutationObserver(() => syncAllRibbon());
    obs.observe(card, {
      attributes: true,
      attributeFilter: ["class"],
      childList: true,
      subtree: true,
      characterData: true,
    });
  }
  syncAllRibbon();

  for (const id of ["p-name", "p-benchmark", "p-date"]) {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", syncCrumbs);
      el.addEventListener("change", syncCrumbs);
    }
  }
  syncCrumbs();

  const ws = document.getElementById("weight-summary");
  if (ws) {
    const obs = new MutationObserver(() => {
      syncMetaChips();
      syncBriefSubs();
    });
    obs.observe(ws, { childList: true, subtree: true, characterData: true });
  }
  const pb = document.getElementById("positions-body");
  if (pb) {
    const obs = new MutationObserver(() => {
      syncMetaChips();
      syncBriefSubs();
    });
    obs.observe(pb, { childList: true, subtree: true });
    pb.addEventListener("input", syncMetaChips);
  }
  syncMetaChips();
  syncBriefSubs();
}

onLocaleChange(() => {
  syncAllRibbon();
  syncCrumbs();
  syncMetaChips();
  syncBriefSubs();
});

export function initLayoutMirror() {
  wireControls();
  startObservers();
}
