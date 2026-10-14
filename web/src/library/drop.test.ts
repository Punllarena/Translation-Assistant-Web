import { describe, expect, it } from "vitest";
import { acceptFiles } from "./drop";

const f = (name: string) => ({ name });

describe("acceptFiles", () => {
  it("keeps accepted extensions regardless of case and reports the rest", () => {
    const { accepted, rejected } = acceptFiles(
      [f("01.txt"), f("G.CSV"), f("cover.png"), f("notes.txt.bak"), f("txt"), f("folder")], [".txt", ".csv"]);
    expect(accepted.map((x) => x.name)).toEqual(["01.txt", "G.CSV"]);
    expect(rejected.map((x) => x.name)).toEqual(["cover.png", "notes.txt.bak", "txt", "folder"]);
  });
  it("handles an empty drop", () => {
    expect(acceptFiles([], [".txt"])).toEqual({ accepted: [], rejected: [] });
  });
});
