/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The web UI talks ONLY to the rest-gateway. In dev we proxy /api -> the gateway
// so the browser never needs CORS and never learns the backend origin.
// Override the target with VITE_API_PROXY (build-time) if the gateway runs elsewhere.
const API_PROXY = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_PROXY,
        changeOrigin: true,
        // SSE: do not buffer; keep the connection open.
        ws: false,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
