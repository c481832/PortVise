import { defineConfig } from "vite";

// Standalone arena GUI, served at "/" by the arena FastAPI app (src/arena/web/app.py).
export default defineConfig({
  root: "frontend/arena",
  base: "/",
  publicDir: "public",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8800",
    },
  },
  build: {
    outDir: "../../src/arena/web/static",
    emptyOutDir: true,
    minify: false,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "app-[hash].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "style-[hash][extname]";
          }
          return "assets/[name]-[hash][extname]";
        },
      },
    },
  },
});
