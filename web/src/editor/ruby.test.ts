import { describe, expect, it } from "vitest";
import {
  alignReading,
  authorRuby,
  generatedRuby,
  placeTokens,
  readingMode,
  type Ruby,
  type Token,
} from "./ruby";

const tok = (surface: string, kana = "", pos = "名詞"): Token => ({ surface, kana, pos });
const base = (text: string, r: Ruby) => text.slice(r.from, r.to);

describe("readingMode", () => {
  it("accepts the four modes and defaults to off", () => {
    expect(readingMode("romaji")).toBe("romaji");
    expect(readingMode("katakana")).toBe("katakana");
    expect(readingMode("bogus")).toBe("off");
    expect(readingMode(undefined)).toBe("off");
  });
});

describe("authorRuby", () => {
  it("finds a kanji base and hides the reading", () => {
    expect(authorRuby("大(おお)きく")).toEqual([{ from: 0, to: 1, rt: "おお", hide: [1, 5] }]);
  });
  it("finds two rubies on one line", () => {
    const text = "喰(く)い千切(ちぎ)る";
    const r = authorRuby(text);
    expect(r.map((x) => [base(text, x), x.rt])).toEqual([
      ["喰", "く"],
      ["千切", "ちぎ"],
    ]);
  });
  it.each([
    ["STATUS(ステータス)", "STATUS", "ステータス"],
    ["１(ひと)つ", "１", "ひと"],
    ["人々（ひとびと）", "人々", "ひとびと"],
    ["彼はSTATUS(ステータス)", "STATUS", "ステータス"],
    ["超AI(ちょうエーアイ)", "AI", "ちょうエーアイ"],
  ])("%s -> one ruby over %s", (text, b, rt) => {
    const r = authorRuby(text);
    expect(r).toHaveLength(1);
    expect(base(text, r[0])).toBe(b);
    expect(r[0].rt).toBe(rt);
    expect(text.slice(r[0].hide![0], r[0].hide![1])).toMatch(/^[(（].*[)）]$/);
  });
  it.each(["(笑)", "笑(笑)", "（1）", "ABC (note)", "かな(かな)", "漢字()", "漢字(kanji)"])(
    "%s stays as written",
    (text) => {
      expect(authorRuby(text)).toEqual([]);
    },
  );
});

describe("placeTokens", () => {
  it("counts UTF-16 offsets past astral characters", () => {
    const placed = placeTokens("𠮷野家に行く", [tok("𠮷野家"), tok("に"), tok("行く")]);
    expect(placed.map((p) => p.from)).toEqual([0, 4, 5]);
    expect(placed[0].to).toBe(4);
  });
  it("skips spaces between tokens", () => {
    const placed = placeTokens("今日は 晴れ", [tok("今日"), tok("は"), tok("晴れ")]);
    expect(placed[2]).toMatchObject({ from: 4, to: 6 });
  });
  it("skips a token that is not found and keeps the cursor", () => {
    const placed = placeTokens("今日は", [tok("今日"), tok("明日"), tok("は")]);
    expect(placed.map((p) => [p.token.surface, p.from])).toEqual([
      ["今日", 0],
      ["は", 2],
    ]);
  });
});

describe("alignReading", () => {
  it.each([
    ["大きく", "オオキク", [{ from: 0, to: 1, rt: "オオ" }]],
    [
      "動き出す",
      "ウゴキダス",
      [
        { from: 0, to: 1, rt: "ウゴ" },
        { from: 2, to: 3, rt: "ダ" },
      ],
    ],
    ["人々", "ヒトビト", [{ from: 0, to: 2, rt: "ヒトビト" }]],
    ["今日", "キョウ", [{ from: 0, to: 2, rt: "キョウ" }]],
    ["行っ", "イッ", [{ from: 0, to: 1, rt: "イ" }]],
    ["大きく", "ダイ", [{ from: 0, to: 3, rt: "ダイ" }]],
    ["大きく", "おおきく", [{ from: 0, to: 1, rt: "オオ" }]],
  ])("%s / %s", (surface, kana, out) => {
    expect(alignReading(surface, kana)).toEqual(out);
  });
  it("gives nothing for kana-only or empty readings", () => {
    expect(alignReading("なったら", "ナッタラ")).toEqual([]);
    expect(alignReading("大", "")).toEqual([]);
  });
});

describe("generatedRuby", () => {
  it("is empty when off", () => {
    expect(generatedRuby("大きく", [tok("大きく", "オオキク", "形容詞")], "off", [])).toEqual([]);
  });
  it("puts hiragana over the kanji only", () => {
    expect(generatedRuby("大きく", [tok("大きく", "オオキク", "形容詞")], "hiragana", [])).toEqual([
      { from: 0, to: 1, rt: "おお" },
    ]);
  });
  it("keeps katakana in katakana mode", () => {
    expect(generatedRuby("大きく", [tok("大きく", "オオキク", "形容詞")], "katakana", [])).toEqual([
      { from: 0, to: 1, rt: "オオ" },
    ]);
  });
  it("merges 助動詞 into the previous token in romaji", () => {
    const tokens = [tok("なっ", "ナッ", "動詞"), tok("たら", "タラ", "助動詞")];
    expect(generatedRuby("なったら", tokens, "romaji", [])).toEqual([
      { from: 0, to: 4, rt: "nattara" },
    ]);
  });
  it("reads particles as particles and skips Latin text", () => {
    expect(generatedRuby("は", [tok("は", "ハ", "助詞")], "romaji", [])).toEqual([
      { from: 0, to: 1, rt: "wa" },
    ]);
    expect(generatedRuby("promise", [tok("promise", "", "名詞")], "romaji", [])).toEqual([]);
    expect(generatedRuby("promise", [tok("promise", "プロミス", "名詞")], "romaji", [])).toEqual([]);
  });
  it("skips tokens with no reading", () => {
    expect(generatedRuby("大", [tok("大", "", "名詞")], "hiragana", [])).toEqual([]);
  });

  describe("with author ruby", () => {
    const text = "大(おお)きく";
    const author = authorRuby(text);
    // MeCab over the shown text: the brackets split it.
    const tokens = [
      tok("大", "ダイ", "名詞"),
      tok("(", "", "補助記号"),
      tok("おお", "オオ", "感動詞"),
      tok(")", "", "補助記号"),
      tok("きく", "キク", "動詞"),
    ];

    it("hiragana keeps the author reading as written and drops the generated one", () => {
      expect(generatedRuby(text, tokens, "hiragana", author)).toEqual([
        { from: 0, to: 1, rt: "おお", hide: [1, 5] },
      ]);
    });
    it("katakana converts the author reading", () => {
      expect(generatedRuby(text, tokens, "katakana", author)).toEqual([
        { from: 0, to: 1, rt: "オオ", hide: [1, 5] },
      ]);
    });
    it("romaji converts the author reading and reads the rest of the word", () => {
      expect(generatedRuby(text, tokens, "romaji", author)).toEqual([
        { from: 0, to: 1, rt: "ō", hide: [1, 5] },
        { from: 5, to: 7, rt: "kiku" },
      ]);
    });
    it("romaji keeps the token's remaining kana when a word runs past the base", () => {
      // A token covering the author base and the okurigana after it.
      const t = "千切る";
      const a: Ruby[] = [{ from: 0, to: 2, rt: "ちぎ" }];
      expect(generatedRuby(t, [tok("千切る", "チギル", "動詞")], "romaji", a)).toEqual([
        { from: 0, to: 2, rt: "chigi" },
        { from: 2, to: 3, rt: "ru" },
      ]);
    });
    it("results are sorted and never overlap", () => {
      const t = "喰(く)い千切(ちぎ)る";
      const a = authorRuby(t);
      const ts = [
        tok("喰", "ク", "動詞"),
        tok("(", ""),
        tok("く", "ク", "動詞"),
        tok(")", ""),
        tok("い", "イ", "動詞"),
        tok("千切", "センギリ", "名詞"),
        tok("(", ""),
        tok("ちぎ", "チギ", "名詞"),
        tok(")", ""),
        tok("る", "ル", "助動詞"),
      ];
      for (const mode of ["hiragana", "katakana", "romaji"] as const) {
        const out = generatedRuby(t, ts, mode, a);
        for (let i = 1; i < out.length; i++) {
          const prevEnd = Math.max(out[i - 1].to, out[i - 1].hide?.[1] ?? 0);
          expect(out[i].from).toBeGreaterThanOrEqual(prevEnd);
        }
      }
    });
  });
});
