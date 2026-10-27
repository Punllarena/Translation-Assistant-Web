// Kana script conversion and Hepburn romaji (pure; used by the reading aid).

const shift = (s: string, from: number, to: number, delta: number): string =>
  Array.from(s, (c) => {
    const n = c.codePointAt(0)!;
    return n >= from && n <= to ? String.fromCodePoint(n + delta) : c;
  }).join("");

export const toHiragana = (s: string): string => shift(s, 0x30a1, 0x30f6, -0x60);
export const toKatakana = (s: string): string => shift(s, 0x3041, 0x3096, 0x60);

const BASE: Record<string, string> = {};
const rows: [string, string[]][] = [
  ["", ["あ", "い", "う", "え", "お"]],
  ["k", ["か", "き", "く", "け", "こ"]],
  ["g", ["が", "ぎ", "ぐ", "げ", "ご"]],
  ["s", ["さ", "し", "す", "せ", "そ"]],
  ["z", ["ざ", "じ", "ず", "ぜ", "ぞ"]],
  ["t", ["た", "ち", "つ", "て", "と"]],
  ["d", ["だ", "ぢ", "づ", "で", "ど"]],
  ["n", ["な", "に", "ぬ", "ね", "の"]],
  ["h", ["は", "ひ", "ふ", "へ", "ほ"]],
  ["b", ["ば", "び", "ぶ", "べ", "ぼ"]],
  ["p", ["ぱ", "ぴ", "ぷ", "ぺ", "ぽ"]],
  ["m", ["ま", "み", "む", "め", "も"]],
  ["r", ["ら", "り", "る", "れ", "ろ"]],
];
rows.forEach(([c, ks]) => ks.forEach((k, i) => (BASE[k] = c + "aiueo"[i])));
Object.assign(BASE, {
  し: "shi", ち: "chi", つ: "tsu", ふ: "fu", じ: "ji", ぢ: "ji", づ: "zu",
  や: "ya", ゆ: "yu", よ: "yo", わ: "wa", を: "o", ゐ: "i", ゑ: "e", ゔ: "vu",
  ゕ: "ka", ゖ: "ke",
});

const SMALL_Y: Record<string, string> = { ゃ: "a", ゅ: "u", ょ: "o" };
const SMALL_V: Record<string, string> = { ぁ: "a", ぃ: "i", ぅ: "u", ぇ: "e", ぉ: "o" };
const MACRON: Record<string, string> = { a: "ā", i: "ī", u: "ū", e: "ē", o: "ō" };
const PARTICLE: Record<string, string> = { は: "wa", へ: "e", を: "o" };

function combine(first: string, small: string): string | null {
  const base = BASE[first];
  if (!base) return null;
  const stem = base.slice(0, -1);
  if (small in SMALL_Y) {
    const y = /(sh|ch|j)$/.test(stem) ? "" : "y";
    return stem + y + SMALL_Y[small];
  }
  if (small in SMALL_V) {
    const v = SMALL_V[small];
    if (first === "う") return "w" + v;
    if (first === "ゔ") return "v" + v;
    if (first === "て" || first === "で") return stem + v; // ti, di (tyu-style ゅ handled above)
    if (first === "と" || first === "ど") return stem + v; // tu, du
    if (first === "ふ") return "f" + v;
    return stem + v; // she, che, je, tsa, ...
  }
  return null;
}

/** Hepburn romaji for `kana`. `pos` is the MeCab part of speech of the word the kana belongs to:
 * 助詞 reads は/へ/を by sound, 動詞 keeps a final う short. */
export function toRomaji(kana: string, pos?: string): string {
  const s = toHiragana(kana);
  const chars = Array.from(s);
  const units: string[] = []; // romaji pieces; "っ", "ん", "ー" kept symbolic
  for (let i = 0; i < chars.length; i++) {
    const c = chars[i];
    const next = chars[i + 1];
    if (c === "っ" || c === "ん" || c === "ー") {
      units.push(c);
      continue;
    }
    if (next && (next in SMALL_Y || next in SMALL_V)) {
      const r = combine(c, next);
      if (r) {
        units.push(r);
        i++;
        continue;
      }
    }
    if (pos === "助詞" && c in PARTICLE) units.push(PARTICLE[c]);
    else units.push(BASE[c] ?? c);
  }
  let out = "";
  for (let i = 0; i < units.length; i++) {
    const u = units[i];
    if (u === "っ") {
      const n = units[i + 1];
      if (n && /^[a-z]/.test(n) && !/^[aiueon]/.test(n) && n !== "ー") {
        out += n.startsWith("ch") ? "t" : n[0];
      }
    } else if (u === "ん") {
      const n = units[i + 1];
      out += n && /^[aiueoy]/.test(n) ? "n'" : "n";
    } else if (u === "ー") {
      const m = out.match(/[aiueo]$/);
      if (m) out = out.slice(0, -1) + MACRON[m[0]]; // ー always gets a macron, even after i
    } else out += u;
  }
  // A verb's own final う is a separate sound (思う omou, 吸う suu), never a long vowel.
  const verbU = pos === "動詞" && chars[chars.length - 1] === "う" && units[units.length - 1] === "u";
  const body = verbU ? out.slice(0, -1) : out;
  const long = body
    .replace(/oo|ou/g, "ō")
    .replace(/uu/g, "ū")
    .replace(/aa/g, "ā")
    .replace(/ee/g, "ē");
  return verbU ? long + "u" : long;
}
