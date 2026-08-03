import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The existing FastAPI route serves flat files from api/admin_static/ at
// /admin/assets/{filename}, whitelisting only {admin.css, admin.js, favicon.svg}.
// base + assetsDir + fixed output names keep the built artefacts compatible
// with that route without any backend change.
export default defineConfig({
  root: "frontend",
  base: "/admin/assets/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../api/admin_static",
    assetsDir: ".",
    emptyOutDir: true,
    // No code-splitting: one admin.js + one admin.css, served by the whitelist.
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "admin.js",
        chunkFileNames: "admin.js",
        assetFileNames: "admin.css",
        inlineDynamicImports: true,
      },
    },
  },
  server: {
    open: "/admin/assets/",
    proxy: {
      "/admin/api": "http://localhost:8082",
    },
  },
});
