import { describe, expect, it } from "vitest";
import { friendlyError } from "./cardCopy";

describe("friendlyError", () => {
  it("names the backend a network failure could not reach", () => {
    expect(friendlyError("Failed to fetch", "DeepL"))
      .toBe("Couldn't reach DeepL. Retry, or check Settings → Machine translation.");
    expect(friendlyError("The server took too long to answer.", "LibreTranslate"))
      .toBe("Couldn't reach LibreTranslate. Retry, or check Settings → Machine translation.");
  });

  it("says where rejected credentials are fixed", () => {
    expect(friendlyError("401 Unauthorized", "DeepL"))
      .toBe("Credentials rejected. Check them in Settings → Machine translation.");
    expect(friendlyError("403: the API key is invalid", "LibreTranslate"))
      .toBe("Credentials rejected. Check them in Settings → Machine translation.");
  });

  it("keeps any other message unchanged", () => {
    expect(friendlyError("The server answered 500.")).toBe("The server answered 500.");
    expect(friendlyError("Something the backend said", "Ollama")).toBe("Something the backend said");
  });
});
