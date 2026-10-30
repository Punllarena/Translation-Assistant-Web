import { describe, expect, it } from "vitest";
import { parseView } from "../library/viewPref";
import { resolvePref } from "./useAccountPref";

describe("resolvePref", () => {
  it("account wins", () => expect(resolvePref("list", true, "shelf", parseView, "shelf"))
    .toEqual({ value: "list", upload: null }));

  it("browser value is uploaded once when the account has none", () =>
    expect(resolvePref(undefined, false, "list", parseView, "shelf")).toEqual({ value: "list", upload: "list" }));

  it("nothing anywhere", () =>
    expect(resolvePref(undefined, false, null, parseView, "shelf")).toEqual({ value: "shelf", upload: null }));
});
