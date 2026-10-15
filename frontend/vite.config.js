import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import process from "node:process";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const apiTarget = process.env.LUMBRE_API_TARGET || "http://127.0.0.1:8501";

export default defineConfig({
  root: frontendRoot,
  plugins: [react()],
  base: "/",
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    open: false,
    proxy: {
      "/api": apiTarget,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    open: false,
  },
  build: {
    outDir: "../web",
    emptyOutDir: true,
  },
});
