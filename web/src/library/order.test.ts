import { describe, expect, it } from "vitest";
import { moveItem, shiftIndex } from "./order";

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

describe("shiftIndex", () => {
  it("refuses to move above the first", () => expect(shiftIndex(0, -1, 3)).toBeNull());
  it("refuses to move below the last", () => expect(shiftIndex(2, 1, 3)).toBeNull());
  it("moves down", () => expect(shiftIndex(1, 1, 3)).toBe(2));
  it("moves up", () => expect(shiftIndex(1, -1, 3)).toBe(0));
});
