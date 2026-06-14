import { defineConfig } from "vite";

export default defineConfig({
  root: "frontend/advisor",
  base: "/static/",
  publicDir: "public",
  css: {
    postcss: {
      plugins: [],
    },
  },
  build: {
    outDir: "../../src/port/static",
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
