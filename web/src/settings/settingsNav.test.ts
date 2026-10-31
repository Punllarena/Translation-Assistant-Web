import { describe, expect, it } from "vitest";
import { ADMIN, PERSONAL, isSettingsPath } from "./settingsNav";

describe("settings navigation", () => {
  it("marks /settings and everything under it, and nothing else", () => {
    expect(isSettingsPath("/settings/admin/server")).toBe(true);
    expect(isSettingsPath("/settings")).toBe(true);
    expect(isSettingsPath("/settingsx")).toBe(false);
    expect(isSettingsPath("/")).toBe(false);
  });

  it("lists the four admin sections in sidebar order", () => {
    expect(ADMIN.map((i) => i.to)).toEqual([
      "/settings/admin/server",
      "/settings/admin/invites",
      "/settings/admin/dictionary",
      "/settings/admin/backup",
    ]);
    expect(ADMIN.map((i) => i.label)).toEqual(["Server", "Invites", "Dictionary", "Backup & restore"]);
  });

  it("lists the four personal sections in sidebar order", () => {
    expect(PERSONAL.map((i) => i.label)).toEqual(["Editor", "Machine translation", "WordPress", "Shortcuts"]);
  });
});
