import { rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { E2E_DB } from "../playwright.config";

export default function globalSetup() {
  rmSync(new URL("../.e2e-data", import.meta.url), { recursive: true, force: true });
  execFileSync("python", ["-m", "tools.e2e_seed"], {
    cwd: "..",
    stdio: "inherit",
    env: { ...process.env, TA_DATABASE_URL: E2E_DB, TA_SECRET_KEY: process.env.TA_SECRET_KEY ?? "e2e-secret-key-at-least-32-characters-long" },
  });
}
