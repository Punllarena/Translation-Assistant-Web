import { describe, expect, it } from "vitest";
import { summaryStatus } from "./summaryStatus";

describe("summaryStatus", () => {
  it("blank text is muted", () => {
    expect(summaryStatus({ text: "  ", pending: false, error: "" })).toEqual({
      tone: "muted",
      message: "Not set. Clearing it does not remove the summary already on WordPress.",
    });
  });
  it("pending with an error", () => {
    expect(summaryStatus({ text: "x", pending: true, error: "boom" })).toEqual({
      tone: "error",
      message: "Last send failed: boom. It will be tried again with the next chapter you publish.",
    });
  });
  it("pending", () => {
    expect(summaryStatus({ text: "x", pending: true, error: "" })).toEqual({
      tone: "muted",
      message: "Waiting: goes out with the next chapter you publish.",
    });
  });
  it("sent", () => {
    expect(summaryStatus({ text: "x", pending: false, error: "" })).toEqual({ tone: "ok", message: "On WordPress." });
  });
});
