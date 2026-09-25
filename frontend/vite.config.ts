/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, proxy: { "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000", ws: true, changeOrigin: true } } },
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./tests/setup.ts"], css: false, include: ["tests/**/*.test.{ts,tsx}"] },
});
