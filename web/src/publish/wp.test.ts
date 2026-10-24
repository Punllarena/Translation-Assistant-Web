import { describe, expect, it } from "vitest";
import { asksOverwrite, ILLUSTRATIONS_LIVE, slugify, tocUrl } from "./wp";

describe("slugify (desktop wp_publisher.slugify)", () => {
  it.each([
    ["Sword of the Wanderer", "sword-of-the-wanderer"],
    ["Hello, World!", "hello-world"],
    ["  --a  --  b--  ", "a-b"],
    ["剣の放浪者", ""],
  ])("%s", (input, out) => expect(slugify(input)).toBe(out));
});

describe("tocUrl (desktop toc_page_url)", () => {
  it("strips the publish path and trailing slashes", () => {
    expect(tocUrl("https://x.com/wp-json/ta-publisher/v1/publish/", "s")).toBe("https://x.com/s/");
    expect(tocUrl("https://x.com", "s")).toBe("https://x.com/s/");
  });
});

describe("asksOverwrite", () => {
  it("only for the already-published 409", () => {
    expect(asksOverwrite(409, ILLUSTRATIONS_LIVE)).toBe(true);
    expect(asksOverwrite(409, "an illustrations upload is already queued or running")).toBe(false);
    expect(asksOverwrite(422, ILLUSTRATIONS_LIVE)).toBe(false);
  });
});
