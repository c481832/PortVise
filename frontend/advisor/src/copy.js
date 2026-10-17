import ENGLISH_COPY from "./copy.json";

const ENGLISH_LOCALE = "en-US";

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

export function copy(key, vars = {}) {
  return interpolate(getPathValue(ENGLISH_COPY, key) ?? key, vars);
}

export function copyList(key) {
  return getPathValue(ENGLISH_COPY, key);
}

export function formatCurrency(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPrice(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(ENGLISH_LOCALE, options).format(value);
}

export function formatDateTime(value) {
  return new Intl.DateTimeFormat(ENGLISH_LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
