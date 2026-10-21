import COPY from "./copy.json";

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
  return interpolate(getPathValue(COPY, key) ?? key, vars);
}

export function copyList(key) {
  return getPathValue(COPY, key);
}
