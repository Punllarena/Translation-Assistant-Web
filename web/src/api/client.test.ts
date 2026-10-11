import { describe, expect, it } from "vitest";
import { ApiError, call, errorMessage } from "./client";

describe("errorMessage", () => {
  it("reads a string detail", () => {
    expect(errorMessage({ detail: "not found" })).toBe("not found");
  });
  it("joins validation errors without the body/query prefix", () => {
    expect(
      errorMessage({ detail: [{ loc: ["body", "title"], msg: "too short" }, { loc: [], msg: "bad" }] }),
    ).toBe("title: too short; bad");
  });
  it("falls back when there is no detail", () => {
    expect(errorMessage(undefined)).toBe("request failed");
  });
});

describe("call", () => {
  it("throws ApiError with the status", async () => {
    const failed = Promise.resolve({ error: { detail: "nope" }, response: new Response(null, { status: 401 }) });
    await expect(call(failed)).rejects.toMatchObject({ status: 401, message: "nope" });
    await expect(call(failed)).rejects.toBeInstanceOf(ApiError);
  });
  it("returns data on success", async () => {
    const ok = Promise.resolve({ data: { id: 1 }, response: new Response(null, { status: 200 }) });
    await expect(call(ok)).resolves.toEqual({ id: 1 });
  });
});
