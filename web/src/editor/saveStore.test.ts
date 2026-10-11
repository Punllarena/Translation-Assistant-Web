import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSaveStore, type Edit } from "./saveStore";

function deferred() {
  let resolve!: () => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<void>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("save store", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces edits into one save", async () => {
    const calls: Edit[][] = [];
    const store = createSaveStore({ save: async (edits) => { calls.push(edits); } });
    store.edit(1, "a");
    store.edit(2, "b");
    store.edit(1, "a2");
    expect(store.getState().state).toBe("unsaved");
    await vi.advanceTimersByTimeAsync(799);
    expect(calls).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls).toEqual([[{ line_number: 1, translated_text: "a2" }, { line_number: 2, translated_text: "b" }]]);
    expect(store.getState().state).toBe("saved");
    expect(store.pending()).toBe(false);
  });

  it("does not call an edit made during a save saved", async () => {
    const first = deferred();
    const calls: Edit[][] = [];
    const store = createSaveStore({
      save: (edits) => { calls.push(edits); return calls.length === 1 ? first.promise : Promise.resolve(); },
    });
    store.edit(1, "a");
    const flushing = store.flush();
    expect(store.getState().state).toBe("saving");
    store.edit(1, "ab");
    first.resolve();
    await flushing;
    expect(store.getState().state).toBe("unsaved");
    expect(store.unsaved()).toEqual([{ line_number: 1, translated_text: "ab" }]);
    await vi.advanceTimersByTimeAsync(800);
    expect(calls[1]).toEqual([{ line_number: 1, translated_text: "ab" }]);
    expect(store.getState().state).toBe("saved");
  });

  it("keeps edits and reports the error when a save fails, then retries", async () => {
    let fail = true;
    const store = createSaveStore({ save: async () => { if (fail) throw new Error("offline"); } });
    store.edit(3, "x");
    await store.flush();
    expect(store.getState()).toEqual({ state: "error", error: "offline" });
    expect(store.unsaved()).toEqual([{ line_number: 3, translated_text: "x" }]);
    fail = false;
    await store.flush();
    expect(store.getState()).toEqual({ state: "saved", error: null });
  });

  it("clears only the lines it sent; lines past the batch cap stay dirty", async () => {
    const calls: Edit[][] = [];
    const store = createSaveStore({ save: async (edits) => { calls.push(edits); } });
    for (let i = 1; i <= 5001; i++) store.edit(i, `t${i}`);
    await store.flush();
    expect(calls[0]).toHaveLength(5000);
    expect(store.getState().state).toBe("unsaved");
    expect(store.unsaved()).toEqual([{ line_number: 5001, translated_text: "t5001" }]);
    await store.flush();
    expect(calls[1]).toEqual([{ line_number: 5001, translated_text: "t5001" }]);
    expect(store.getState().state).toBe("saved");
  });

  it("a flush during a save resolves only after a follow-up save of the new edits", async () => {
    const first = deferred();
    const second = deferred();
    const calls: Edit[][] = [];
    const store = createSaveStore({
      save: (edits) => { calls.push(edits); return calls.length === 1 ? first.promise : second.promise; },
    });
    store.edit(1, "a");
    const firstFlush = store.flush();
    store.edit(1, "ab");
    let resolved = false;
    const waiting = store.flush().then(() => { resolved = true; });
    first.resolve();
    await firstFlush;
    await vi.advanceTimersByTimeAsync(0);
    expect(calls[1]).toEqual([{ line_number: 1, translated_text: "ab" }]);
    expect(resolved).toBe(false);
    second.resolve();
    await waiting;
    expect(resolved).toBe(true);
    expect(store.getState().state).toBe("saved");
  });

  it("a save that throws synchronously ends in the error state", async () => {
    const store = createSaveStore({
      save: () => { throw new Error("boom"); },
    });
    store.edit(1, "a");
    await store.flush();
    expect(store.getState()).toEqual({ state: "error", error: "boom" });
    expect(store.unsaved()).toEqual([{ line_number: 1, translated_text: "a" }]);
  });

  it("flush with nothing dirty saves nothing", async () => {
    const save = vi.fn(async () => {});
    const store = createSaveStore({ save });
    await store.flush();
    expect(save).not.toHaveBeenCalled();
    expect(store.getState().state).toBe("saved");
  });

  it("flushOnExit sends everything with keepalive", () => {
    const save = vi.fn(async () => {});
    const store = createSaveStore({ save });
    store.edit(1, "a");
    store.flushOnExit();
    expect(save).toHaveBeenCalledWith([{ line_number: 1, translated_text: "a" }], true);
  });

  it("notifies subscribers and keeps a stable snapshot between changes", () => {
    const store = createSaveStore({ save: async () => {} });
    const fn = vi.fn();
    const off = store.subscribe(fn);
    const before = store.getState();
    expect(store.getState()).toBe(before);
    store.edit(1, "a");
    expect(fn).toHaveBeenCalled();
    expect(store.getState()).not.toBe(before);
    off();
  });
});
