import { describe, expect, it } from "vitest";
import { friendlyError } from "./cardCopy";

describe("friendlyError", () => {
  it("names the backend a network failure could not reach", () => {
    const network = "Couldn't reach DeepL. Retry, or check Settings → Machine translation.";
    for (const said of ["Failed to fetch", "NetworkError when attempting to fetch", "ECONNREFUSED",
      "getaddrinfo ENOTFOUND deepl.example", "timed out", "request timeout", "host unreachable",
      "connection reset by peer"]) {
      expect(friendlyError(said, "DeepL")).toBe(network);
    }
  });

  it("says where rejected credentials are fixed", () => {
    const credentials = "Credentials rejected. Check them in Settings → Machine translation.";
    for (const said of ["401 Unauthorized", "403: the API key is invalid", "Authentication failed"]) {
      expect(friendlyError(said, "LibreTranslate")).toBe(credentials);
    }
  });

  it("keeps any other message unchanged", () => {
    // Answers the backend gave, not a lost connection.
    for (const said of ["The server took too long to answer.", "Abort", "the abort was cancelled",
      "dns", "dns lookup skipped", "The server answered 500.", "Something the backend said"]) {
      expect(friendlyError(said, "Ollama")).toBe(said);
    }
  });
});
