const DEFAULT_LOCALE = "en";
const LOCALE_CATALOG_VERSION = "20260522-layout-b";
const SUPPORTED_LOCALES = new Set(["en", "zh-CN"]);
const LOCALE_STORAGE_KEY = "portAdvisorLocale";
const catalogs = new Map();
const listeners = new Set();
let activeLocale = DEFAULT_LOCALE;

function getPathValue(obj, key) {
  return String(key || "")
    .split(".")
    .reduce((acc, part) => (acc && typeof acc === "object" ? acc[part] : undefined), obj);
}

function interpolate(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, key) => {
    const value = vars[key];
    return value == null ? "" : String(value);
  });
}

export function normalizeLocale(value) {
  const raw = String(value || "").trim();
  if (!raw) return DEFAULT_LOCALE;
  const lowered = raw.replaceAll("_", "-").toLowerCase();
  if (lowered.startsWith("zh")) return "zh-CN";
  if (lowered.startsWith("en")) return "en";
  return DEFAULT_LOCALE;
}

async function loadCatalog(locale) {
  const resolved = normalizeLocale(locale);
  if (catalogs.has(resolved)) return catalogs.get(resolved);
  const res = await fetch(`/static/locales/${resolved}.json?v=${LOCALE_CATALOG_VERSION}`);
  if (!res.ok) throw new Error(`Failed to load locale catalog: ${resolved}`);
  const data = await res.json();
  catalogs.set(resolved, data);
  return data;
}

export async function initI18n() {
  let saved = "";
  try {
    saved = localStorage.getItem(LOCALE_STORAGE_KEY) || "";
  } catch {
    saved = "";
  }
  const browser = Array.isArray(navigator.languages) && navigator.languages.length
    ? navigator.languages[0]
    : navigator.language;
  await setLocale(saved || browser || DEFAULT_LOCALE, { persist: Boolean(saved) });
}

export async function setLocale(value, { persist = true } = {}) {
  const resolved = normalizeLocale(value);
  await Promise.all([loadCatalog(DEFAULT_LOCALE), loadCatalog(resolved)]);
  activeLocale = resolved;
  document.documentElement.lang = resolved;
  try {
    if (persist) localStorage.setItem(LOCALE_STORAGE_KEY, resolved);
  } catch {
  }
  applyTranslations(document);
  for (const listener of listeners) listener(resolved);
}

export function getLocale() {
  return activeLocale;
}

export function getLocaleLabel(locale) {
  return normalizeLocale(locale) === "zh-CN" ? "简体中文" : "English";
}

export function onLocaleChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function t(key, vars = {}) {
  const current = catalogs.get(activeLocale) || {};
  const fallback = catalogs.get(DEFAULT_LOCALE) || {};
  const value = getPathValue(current, key) ?? getPathValue(fallback, key);
  return interpolate(value ?? key, vars);
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.setAttribute("title", t(el.dataset.i18nTitle));
  });
  root.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
  });
  document.title = t("page.title");
}

export function formatCurrency(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(activeLocale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
    ...options,
  }).format(value);
}

export function formatPrice(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(activeLocale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(activeLocale, options).format(value);
}

export function formatPercent(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(activeLocale, {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    ...options,
  }).format(value);
}

export function formatDateTime(value, options = {}) {
  try {
    return new Intl.DateTimeFormat(activeLocale, {
      dateStyle: "medium",
      timeStyle: "short",
      ...options,
    }).format(new Date(value));
  } catch {
    return "";
  }
}

export function formatSignedNumber(value, digits = 2, { percent = false } = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  const n = Number(value);
  const sign = n >= 0 ? "+" : "";
  if (percent) {
    return `${sign}${formatNumber(Math.abs(n), {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}%`.replace(/^\+-/, "-");
  }
  return `${sign}${formatNumber(Math.abs(n), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`.replace(/^\+-/, "-");
}

export function isSupportedLocale(value) {
  return SUPPORTED_LOCALES.has(normalizeLocale(value));
}
