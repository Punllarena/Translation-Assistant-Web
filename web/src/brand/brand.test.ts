import { describe, expect, it } from "vitest";
import {
  DEFAULT_BRANDING,
  clearCache,
  fromApi,
  headState,
  imageUrl,
  readCache,
  writeCache,
  type Branding,
} from "./brand";

const CACHED: Branding = {
  name: "My Site",
  showName: false,
  logoId: 3,
  logoDarkId: null,
  faviconId: 7,
};

function storage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
  };
}

describe("branding data", () => {
  it("maps the API's snake_case to camelCase, nulls included", () => {
    expect(
      fromApi({
        name: "X",
        show_name: false,
        logo_id: 1,
        logo_dark_id: null,
        favicon_id: 2,
      }),
    ).toEqual({ name: "X", showName: false, logoId: 1, logoDarkId: null, faviconId: 2 });
  });

  it("reads back a written cache", () => {
    const store = storage();
    writeCache(store, CACHED);
    expect(readCache(store)).toEqual(CACHED);
  });

  it("ignores a missing, broken or wrongly shaped cache", () => {
    expect(readCache(storage())).toBeNull();
    expect(readCache(storage({ "ta.brand": "{" }))).toBeNull();
    expect(readCache(storage({ "ta.brand": "null" }))).toBeNull();
    expect(readCache(storage({ "ta.brand": '{"name":5}' }))).toBeNull();
    expect(readCache(storage({ "ta.brand": '{"name":"A","showName":"yes"}' }))).toBeNull();
  });

  it("clears the cache", () => {
    const store = storage();
    writeCache(store, CACHED);
    clearCache(store);
    expect(readCache(store)).toBeNull();
  });

  it("builds image urls", () => {
    expect(imageUrl(7)).toBe("/api/branding/image/7");
  });

  it("names the tab and the default favicon", () => {
    expect(headState(DEFAULT_BRANDING)).toEqual({
      title: "Translation Assistant",
      iconHref: "/favicon.svg",
    });
    expect(headState({ ...DEFAULT_BRANDING, faviconId: 7 })).toEqual({
      title: "Translation Assistant",
      iconHref: "/api/branding/image/7",
    });
  });
});
