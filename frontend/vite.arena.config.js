import { defineConfig } from "vite";
import { appConfig } from "./vite.app.js";

// Arena GUI, served at "/" by the arena FastAPI app (src/arena/web/app.py).
export default defineConfig(
  appConfig({
    root: "frontend/arena",
    base: "/",
    outDir: "../../src/arena/web/ui",
    apiTarget: "http://127.0.0.1:8800",
  }),
);
