import { rmSync } from "node:fs";

// The database reset (tools.e2e_seed) runs in the API webServer command; see playwright.config.ts.
export default function globalSetup() {
  rmSync(new URL("../.e2e-data", import.meta.url), { recursive: true, force: true });
}
