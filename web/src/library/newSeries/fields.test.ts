import { describe, expect, it } from "vitest";
import { appendCredits, epubAuthorDefault, seriesBody } from "./fields";

const v = { title: " T ", originalTitle: " 題 ", originalAuthor: " 山田 ", authorRomaji: " Yamada " };

describe("series fields", () => {
  it("seriesBody trims", () => {
    expect(seriesBody(v)).toEqual({ title: "T", original_title: "題", original_author: "山田", author_romaji: "Yamada" });
  });
  it("appendCredits fills the epub form", () => {
    const f = new FormData();
    appendCredits(f, v);
    expect(f.get("new_series")).toBe("true");
    expect(f.get("series_title")).toBe("T");
    expect(f.get("original_title")).toBe("題");
    expect(f.get("original_author")).toBe("山田");
    expect(f.get("author_romaji")).toBe("Yamada");
  });
  it("epubAuthorDefault prefers romaji", () => {
    expect(epubAuthorDefault("  ", "山田")).toBe("山田");
    expect(epubAuthorDefault("Yamada", "山田")).toBe("Yamada");
  });
});
