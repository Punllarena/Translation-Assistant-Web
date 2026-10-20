import { QueryClient } from "@tanstack/react-query";
import { expect, test } from "vitest";
import { forgetUserData } from "./session";

test("forgetUserData keeps the session and setup queries", () => {
  const qc = new QueryClient();
  qc.setQueryData(["me"], { id: 1 });
  qc.setQueryData(["setup"], { needs_setup: false });
  qc.setQueryData(["series"], []);
  forgetUserData(qc);
  expect(qc.getQueryData(["me"])).toBeDefined();
  expect(qc.getQueryData(["setup"])).toBeDefined();
  expect(qc.getQueryData(["series"])).toBeUndefined();
});
