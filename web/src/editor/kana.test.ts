import { describe, expect, it } from "vitest";
import { toHiragana, toKatakana, toRomaji } from "./kana";

describe("kana scripts", () => {
  it("converts katakana to hiragana and back", () => {
    expect(toHiragana("オオキク")).toBe("おおきく");
    expect(toKatakana("ゆめ")).toBe("ユメ");
  });
  it("leaves other characters and the long mark alone", () => {
    expect(toHiragana("ステーキ abc 漢")).toBe("すてーき abc 漢");
  });
});

describe("toRomaji", () => {
  it.each([
    ["おおきく", "ōkiku"],
    ["しよう", "shiyō"],
    ["ケッコン", "kekkon"],
    ["なったら", "nattara"],
    ["ステータス", "sutētasu"],
    ["ちょっと", "chotto"],
    ["きんえん", "kin'en"],
    ["おいしい", "oishii"],
    ["ティー", "tī"],
    ["ファイル", "fairu"],
    ["まっちゃ", "matcha"],
    ["じゅう", "jū"],
  ])("%s -> %s", (kana, out) => {
    expect(toRomaji(kana)).toBe(out);
  });
  it("reads a few small-kana loanword sounds", () => {
    expect(toRomaji("ティ")).toBe("ti");
    expect(toRomaji("ファ")).toBe("fa");
    expect(toRomaji("シェ")).toBe("she");
  });
  it("keeps a verb's own final う short", () => {
    expect(toRomaji("おもう", "動詞")).toBe("omou");
    expect(toRomaji("スウ", "動詞")).toBe("suu");
    expect(toRomaji("おおきく", "形容詞")).toBe("ōkiku");
    expect(toRomaji("おもう")).toBe("omō");
  });
  it("reads particles by sound only for 助詞", () => {
    expect(toRomaji("は", "助詞")).toBe("wa");
    expect(toRomaji("は")).toBe("ha");
    expect(toRomaji("を", "助詞")).toBe("o");
    expect(toRomaji("へ", "助詞")).toBe("e");
  });
});
