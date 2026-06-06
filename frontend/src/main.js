import "./styles/main.css";
import "./app.js";
import { initLayoutMirror } from "./layout-mirror.js";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLayoutMirror, { once: true });
} else {
  initLayoutMirror();
}
