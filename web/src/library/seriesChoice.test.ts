import { describe, expect, it } from "vitest";
import { seriesChosen } from "./SeriesChoice";

describe("seriesChosen", () => {
  it("rejects an empty choice", () => expect(seriesChosen({ id: "", title: "  " })).toBe(false));
  it("accepts an id", () => expect(seriesChosen({ id: "3", title: "" })).toBe(true));
  it("accepts a new title", () => expect(seriesChosen({ id: "", title: "New" })).toBe(true));
});
