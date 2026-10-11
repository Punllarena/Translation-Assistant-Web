import { defineConfig } from "@playwright/test";

export const E2E_DB = process.env.TA_E2E_DATABASE_URL ?? "postgresql+psycopg://ta:ta@localhost:5432/ta_e2e";
const SECRET = process.env.TA_SECRET_KEY ?? "e2e-secret-key-at-least-32-characters-long";
const API = "http://127.0.0.1:8001";

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 30_000,
  globalSetup: "./e2e/global-setup.ts",
  use: { baseURL: "http://localhost:5174" },
  webServer: [
    {
      command: "cd .. && python -m uvicorn api.main:app --port 8001",
      url: `${API}/healthz`,
      env: { ...process.env, TA_DATABASE_URL: E2E_DB, TA_SECRET_KEY: SECRET, TA_COOKIE_SECURE: "false" } as Record<string, string>,
    },
    {
      command: "npm run dev -- --port 5174 --strictPort",
      url: "http://localhost:5174",
      env: { ...process.env, TA_API_URL: API } as Record<string, string>,
    },
  ],
});
