import { describe, expect, it } from "vitest";
import { groupRuns } from "./syosetuGroups";

describe("groupRuns", () => {
  it("splits the index at each heading", () => {
    const runs = groupRuns([{ n: 1 }, { n: 2, group: "一" }, { n: 3, group: "一" }, { n: 4, group: "二" }]);
    expect(runs.map((r) => [r.group, r.chapters.map((c) => c.n)])).toEqual([
      [null, [1]], ["一", [2, 3]], ["二", [4]],
    ]);
  });
  it("is empty for no chapters", () => expect(groupRuns([])).toEqual([]));
});
