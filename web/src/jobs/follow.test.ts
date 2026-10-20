import { afterEach, describe, expect, it, vi } from "vitest";
import { followJob, isTerminal, startsJob, type Job } from "./follow";

class FakeSource {
  static last: FakeSource;
  listeners: Record<string, (e: { data: string }) => void> = {};
  closed = false;
  onerror: (() => void) | null = null;
  constructor(public url: string) { FakeSource.last = this; }
  addEventListener(type: string, fn: (e: { data: string }) => void) { this.listeners[type] = fn; }
  close() { this.closed = true; }
}

const job = (state: string): Job => ({ id: 1, kind: "syosetu_fetch", state, progress: 1, total: 2,
  message: "", params: {}, result: null, created_at: "", started_at: null, finished_at: null });

const stubFetch = (impl: () => Promise<unknown>) => vi.stubGlobal("fetch", vi.fn(impl));
const reply = (state: string) => () => Promise.resolve({ ok: true, json: () => Promise.resolve(job(state)) });
const flush = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => vi.unstubAllGlobals());

describe("followJob", () => {
  it("reports every update and closes on a terminal state", () => {
    const seen: string[] = [];
    followJob(1, (j) => seen.push(j.state), FakeSource as never);
    const src = FakeSource.last;
    expect(src.url).toBe("/api/jobs/1/events");
    src.listeners.job({ data: JSON.stringify(job("running")) });
    expect(src.closed).toBe(false);
    src.listeners.job({ data: JSON.stringify(job("done")) });
    expect(seen).toEqual(["running", "done"]);
    expect(src.closed).toBe(true);
  });
  it("closes on a connection error so the browser does not reconnect forever", () => {
    stubFetch(reply("running"));
    followJob(1, () => {}, FakeSource as never);
    FakeSource.last.onerror?.();
    expect(FakeSource.last.closed).toBe(true);
  });
  it("delivers a job that finished while the stream was down", async () => {
    stubFetch(reply("done"));
    const seen: string[] = [];
    const onError = vi.fn();
    followJob(1, (j) => seen.push(j.state), FakeSource as never, onError);
    FakeSource.last.onerror?.();
    await flush();
    expect(seen).toEqual(["done"]);
    expect(onError).not.toHaveBeenCalled();
  });
  it("reports an error when the job is still running or cannot be read", async () => {
    const onError = vi.fn();
    stubFetch(reply("running"));
    followJob(1, () => {}, FakeSource as never, onError);
    FakeSource.last.onerror?.();
    await flush();
    expect(onError).toHaveBeenCalledTimes(1);
    stubFetch(() => Promise.reject(new Error("offline")));
    followJob(1, () => {}, FakeSource as never, onError);
    FakeSource.last.onerror?.();
    await flush();
    expect(onError).toHaveBeenCalledTimes(2);
  });
  it("knows the terminal states", () => {
    expect(["done", "failed", "cancelled", "running"].map((s) => isTerminal(job(s))))
      .toEqual([true, true, true, false]);
  });
});

describe("startsJob", () => {
  it("recognises a queued job and a ta.db upload", () => {
    expect(startsJob({ id: 1, kind: "dict_download", state: "queued" })).toBe(true);
    expect(startsJob({ upload_id: "x", job_id: 3 })).toBe(true);
  });
  it("ignores other results", () => {
    expect(startsJob({ kind: "deepl", name: "default" })).toBe(false);
    expect(startsJob(undefined)).toBe(false);
    expect(startsJob(null)).toBe(false);
    expect(startsJob([])).toBe(false);
  });
});
