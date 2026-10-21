import { defineConfig } from "vite";
import { appConfig } from "./vite.app.js";

// Advisor GUI, served at "/ui/" by the advisor FastAPI app (src/advisor/web/app.py).
export default defineConfig(
  appConfig({
    root: "frontend/advisor",
    base: "/ui/",
    outDir: "../../src/advisor/web/ui",
    apiTarget: "http://127.0.0.1:7860",
  }),
);
