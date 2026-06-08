import { defineConfig } from "vite";

// Standalone arena GUI, served at "/" by the arena FastAPI app (arena/web/app.py).
export default defineConfig({
  root: "arena_frontend",
  base: "/",
  publicDir: "public",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8800",
    },
  },
  build: {
    outDir: "../arena/web/static",
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
