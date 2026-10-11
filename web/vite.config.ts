/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Same shape as Caddy in production: /api/* reaches uvicorn without the prefix.
    proxy: {
      "/api": {
        target: process.env.TA_API_URL ?? "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
