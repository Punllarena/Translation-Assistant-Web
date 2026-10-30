import { describe, expect, it } from "vitest";
import { menuPublishLabel, WP_TAG_LABEL, wpTag, wpTagTone } from "./wpTag";

const now = new Date("2026-11-01T12:00:00Z");

describe("wpTag", () => {
  it("scheduled in the future", () => {
    expect(wpTag({ wp_status: "future", wp_scheduled_for: "2026-11-02T00:00:00Z", wp_published_at: null }, now)).toBe("scheduled");
  });

  it("scheduled time passed reads Published?", () => {
    expect(wpTag({ wp_status: "future", wp_scheduled_for: "2026-10-31T00:00:00Z", wp_published_at: null }, now)).toBe("due");
  });

  it("falls back to wp_published_at", () => {
    expect(wpTag({ wp_status: "future", wp_scheduled_for: null, wp_published_at: "2026-10-31T00:00:00Z" }, now)).toBe("due");
  });

  it("future with no dates stays scheduled", () => {
    expect(wpTag({ wp_status: "future", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("scheduled");
  });

  it("other statuses", () => {
    expect(wpTag({ wp_status: "publish", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("published");
    expect(wpTag({ wp_status: "", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("none");
    expect(wpTag({ wp_status: "draft", wp_scheduled_for: "2026-11-02T00:00:00Z", wp_published_at: null }, now)).toBe("none");
  });

  it("labels and tones", () => {
    expect(WP_TAG_LABEL).toEqual({ published: "Published", scheduled: "Scheduled", due: "Published?", none: "Not posted" });
    expect(wpTagTone("published")).toBe("ok");
    expect(wpTagTone("scheduled")).toBe("warn");
    expect(wpTagTone("due")).toBe("muted");
    expect(wpTagTone("none")).toBe("");
  });

  it("menu label", () => {
    expect(menuPublishLabel("scheduled")).toBe("Reschedule…");
    expect(menuPublishLabel("published")).toBe("Update post…");
    expect(menuPublishLabel("due")).toBe("Update post…");
    expect(menuPublishLabel("none")).toBe("Publish…");
  });
});
