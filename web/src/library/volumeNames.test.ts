import { describe, expect, it } from "vitest";
import cases from "./volumeNames.cases.json";
import {
  DEFAULT_TEMPLATE,
  formatIndex,
  label,
  nextVolumeIndex,
  parseTitle,
  prefillName,
  render,
  templateError,
  wpLabel,
} from "./volumeNames";

describe("volumeNames (shared case table)", () => {
  it("exports the default template", () => {
    expect(DEFAULT_TEMPLATE).toBe("{series} - {kind} {index} - {subtitle}");
  });

  it.each(cases.format_index)("formatIndex $in", (c) => {
    expect(formatIndex(c.in)).toBe(c.out);
  });

  it.each(cases.render)("render $template -> $out", (c) => {
    const { template, out, ...v } = c;
    expect(render(template, v)).toBe(out);
  });

  it.each(cases.label)("label $kind $index $subtitle", (c) => {
    expect(label(c.kind, c.index, c.subtitle)).toBe(c.out);
    expect(wpLabel(c.kind, c.index, c.subtitle)).toBe(c.wp);
  });

  it.each(cases.parse)("parseTitle $title", (c) => {
    expect(parseTitle(c.title, c.series)).toEqual({
      kind: c.kind,
      index: c.index,
      subtitle: c.subtitle,
    });
  });

  it.each(cases.templates_invalid)("templateError %s", (t) => {
    expect(templateError(t)).not.toBeNull();
  });

  it("templateError accepts valid templates and names the problem", () => {
    expect(templateError(DEFAULT_TEMPLATE)).toBeNull();
    expect(templateError("{title}")).toContain("{title}");
    expect(templateError("x }")).toContain("}");
  });
});

describe("nextVolumeIndex", () => {
  it("starts at 1", () => expect(nextVolumeIndex([])).toBe("1"));
  it("floors the highest Volume index and adds one", () => {
    expect(
      nextVolumeIndex([
        { kind: "Volume", volume_index: "3.5" },
        { kind: "volume", volume_index: "2" },
        { kind: "Side Story", volume_index: "9" },
      ]),
    ).toBe("4");
  });
  it("ignores unindexed rows", () => {
    expect(nextVolumeIndex([{ kind: "", volume_index: null }])).toBe("1");
  });
});

describe("render placeholder lookup", () => {
  it("renders inherited names as empty", () => {
    const v = { series: "S", kind: "Volume", index: "1", subtitle: "T" };
    expect(render("{constructor} {toString} {kind}", v)).toBe("Volume");
    expect(render("{constructor}", v)).toBe("");
  });
});

describe("prefillName", () => {
  const vols = [{ kind: "Volume", volume_index: "2" }];
  it("a book titled as the series starts as the next Volume", () => {
    expect(prefillName("Mushoku", "mushoku ", vols)).toEqual({ kind: "Volume", index: "3", subtitle: "" });
  });
  it("a new series starts at Volume 1", () => {
    expect(prefillName("Book", "Book", [])).toEqual({ kind: "Volume", index: "1", subtitle: "" });
  });
  it("a volume shape still parses", () => {
    expect(prefillName("Mushoku - Volume 5", "Mushoku", vols)).toEqual({ kind: "Volume", index: "5", subtitle: "" });
  });
  it("another title stays a subtitle", () => {
    expect(prefillName("Prologue", "Mushoku", vols)).toEqual({ kind: "", index: null, subtitle: "Prologue" });
    expect(prefillName("Mushoku", "", vols)).toEqual({ kind: "", index: null, subtitle: "Mushoku" });
  });
});
