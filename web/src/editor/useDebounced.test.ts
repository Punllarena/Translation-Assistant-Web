import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { trailingDebounce } from "./useDebounced";

describe("trailingDebounce", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("applies only the last value once the presses stop", () => {
    const seen: number[] = [];
    const hold = trailingDebounce<number>(400, (v) => seen.push(v));
    for (let line = 1; line <= 5; line++) {
      hold.push(line);
      vi.advanceTimersByTime(100);
    }
    expect(seen).toEqual([]); // still stepping: nothing announced
    vi.advanceTimersByTime(400);
    expect(seen).toEqual([5]);
  });

  it("says nothing for a value whose timer was cancelled", () => {
    const seen: string[] = [];
    const hold = trailingDebounce<string>(400, (v) => seen.push(v));
    hold.push("left the chapter");
    hold.cancel();
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual([]);
  });

  it("keeps a later value after an earlier one was applied", () => {
    const seen: number[] = [];
    const hold = trailingDebounce<number>(400, (v) => seen.push(v));
    hold.push(1);
    vi.advanceTimersByTime(400);
    hold.push(2);
    vi.advanceTimersByTime(400);
    expect(seen).toEqual([1, 2]);
  });
});
