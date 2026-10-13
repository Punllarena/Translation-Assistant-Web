import { describe, expect, it } from "vitest";
import { wpBadge } from "./badge";

describe("wpBadge (desktop picker WP column)", () => {
  const at = new Date(2026, 9, 13, 20, 5).toISOString();
  it("labels published and scheduled chapters with their date", () => {
    expect(wpBadge({ wp_status: "publish", wp_published_at: at })).toBe("pub 10/13 20:05");
    expect(wpBadge({ wp_status: "future", wp_published_at: at })).toBe("sched 10/13 20:05");
  });
  it("is the bare tag without a date and empty otherwise", () => {
    expect(wpBadge({ wp_status: "publish", wp_published_at: null })).toBe("pub");
    expect(wpBadge({ wp_status: "draft", wp_published_at: at })).toBe("");
    expect(wpBadge({ wp_status: "", wp_published_at: null })).toBe("");
  });
});
