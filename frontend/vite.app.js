// Shared Vite settings for the advisor and arena frontends.
export function appConfig({ root, base, outDir, apiTarget }) {
  return {
    root,
    base,
    publicDir: "public",
    server: {
      proxy: { "/api": apiTarget },
    },
    // An empty plugin list stops Vite from picking up a postcss config from a parent directory.
    css: {
      postcss: { plugins: [] },
    },
    build: {
      outDir,
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
  };
}
