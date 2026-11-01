import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { saveFailure } from "./saveErrors";

describe("save failure", () => {
  it("names a server error and says it may pass", () => {
    expect(saveFailure(new ApiError(500, "x"))).toEqual({ message: "The server answered 500.", permanent: false });
  });

  it("treats a vanished chapter as final", () => {
    expect(saveFailure(new ApiError(404, "Not found")))
      .toEqual({ message: "This chapter no longer exists on the server.", permanent: true });
  });

  it("hides a validation body behind plain words", () => {
    expect(saveFailure(new ApiError(422, "lines.0.translated_text: …")))
      .toEqual({ message: "The server refused this text. It may be too long.", permanent: true });
  });

  it("treats any other refusal as final", () => {
    expect(saveFailure(new ApiError(403, "x"))).toEqual({ message: "The server refused the save (403).", permanent: true });
  });

  it("keeps trying when the trouble may pass", () => {
    for (const s of [401, 408, 429, 503]) expect(saveFailure(new ApiError(s, "x")).permanent).toBe(false);
  });

  it("names a dead connection and a timeout", () => {
    expect(saveFailure(new TypeError("Failed to fetch"))).toEqual({ message: "The server can't be reached.", permanent: false });
    expect(saveFailure(new DOMException("", "TimeoutError")))
      .toEqual({ message: "The server took too long to answer.", permanent: false });
  });

  it("passes on any other message", () => {
    expect(saveFailure(new Error("boom"))).toEqual({ message: "boom", permanent: false });
  });
});
