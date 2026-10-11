import { describe, expect, it } from "vitest";
import { moveItem } from "./order";

describe("moveItem", () => {
  it("moves down", () => expect(moveItem(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]));
  it("moves up", () => expect(moveItem(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]));
  it("same place is a copy", () => {
    const items = ["a", "b"];
    const moved = moveItem(items, 1, 1);
    expect(moved).toEqual(items);
    expect(moved).not.toBe(items);
  });
  it("does not mutate its input", () => {
    const items = ["a", "b", "c"];
    moveItem(items, 0, 2);
    expect(items).toEqual(["a", "b", "c"]);
  });
});
