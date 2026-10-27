import { describe, expect, it } from "vitest";
import { backupProblem } from "./backupForm";

const PASS = "correct horse battery";

describe("backupProblem", () => {
  it("passes a matching pair long enough to restore from", () => {
    expect(backupProblem(PASS, PASS, false)).toBeNull();
  });

  it("refuses a short passphrase", () => {
    expect(backupProblem("short", "short", false)).toBe("Use at least 12 characters.");
  });

  it("refuses a mismatch", () => {
    expect(backupProblem(PASS, `${PASS} `, false)).toBe("The passphrases do not match.");
  });

  it("refuses while a restore runs", () => {
    expect(backupProblem(PASS, PASS, true)).toBe("A restore is in progress.");
  });

  it("puts the restore first, even with a short passphrase", () => {
    expect(backupProblem("short", "", true)).toBe("A restore is in progress.");
  });
});
