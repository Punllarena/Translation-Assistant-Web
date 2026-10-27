// Where readings go over Japanese source text (pure): author ruby already in the text
// (`漢字(かんじ)`), MeCab readings aligned to kanji, and API tokens placed on the shown text.
// All offsets are UTF-16 offsets into the shown text.
import type { Schemas } from "../api/client";
import { toHiragana, toKatakana, toRomaji } from "./kana";

export type Token = Schemas["ReadingToken"];
export type ReadingMode = "off" | "hiragana" | "katakana" | "romaji";

/** `[from, to)` is the base; `hide` is the `(reading)` range, brackets included, not drawn as text. */
export interface Ruby {
  from: number;
  to: number;
  rt: string;
  hide?: [number, number];
}

const MODES: readonly ReadingMode[] = ["off", "hiragana", "katakana", "romaji"];
export const readingMode = (v: unknown): ReadingMode =>
  MODES.includes(v as ReadingMode) ? (v as ReadingMode) : "off";

const isKanji = (cp: number): boolean =>
  (cp >= 0x4e00 && cp <= 0x9fff) ||
  (cp >= 0x3400 && cp <= 0x4dbf) ||
  (cp >= 0xf900 && cp <= 0xfaff) ||
  (cp >= 0x20000 && cp <= 0x3ffff) ||
  cp === 0x3005 || // 々
  cp === 0x3006 || // 〆
  cp === 0x3007 || // 〇
  cp === 0x30f6; // ヶ
const isKana = (cp: number): boolean =>
  ((cp >= 0x3041 && cp <= 0x3096) || (cp >= 0x30a1 && cp <= 0x30fa) || cp === 0x30fc) &&
  cp !== 0x30f6;
const isLatin = (cp: number): boolean =>
  (cp >= 0x30 && cp <= 0x39) ||
  (cp >= 0x41 && cp <= 0x5a) ||
  (cp >= 0x61 && cp <= 0x7a) ||
  (cp >= 0xff10 && cp <= 0xff19) ||
  (cp >= 0xff21 && cp <= 0xff3a) ||
  (cp >= 0xff41 && cp <= 0xff5a);
const isJapanese = (s: string): boolean =>
  Array.from(s).some((c) => isKanji(c.codePointAt(0)!) || isKana(c.codePointAt(0)!));
const allKana = (s: string): boolean => s !== "" && Array.from(s).every((c) => isKana(c.codePointAt(0)!));
const hasKanji = (s: string): boolean => Array.from(s).some((c) => isKanji(c.codePointAt(0)!));

/** The code point ending just before UTF-16 offset `i`, with its start offset. */
function before(text: string, i: number): { cp: number; at: number } | null {
  if (i <= 0) return null;
  const lo = text.charCodeAt(i - 1);
  if (lo >= 0xdc00 && lo <= 0xdfff && i >= 2) {
    const hi = text.charCodeAt(i - 2);
    if (hi >= 0xd800 && hi <= 0xdbff) return { cp: text.codePointAt(i - 2)!, at: i - 2 };
  }
  return { cp: lo, at: i - 1 };
}

const AUTHOR = /\(([^()（）]*)\)|（([^()（）]*)）/g;

/** Ruby written in the text as `base(reading)`: the base is the run of one kind (kanji, or Latin
 * letters and digits) right before the bracket; the reading must be kana only. */
export function authorRuby(text: string): Ruby[] {
  const out: Ruby[] = [];
  for (const m of text.matchAll(AUTHOR)) {
    const rt = m[1] ?? m[2];
    const open = m.index!;
    if (!allKana(rt)) continue;
    const last = before(text, open);
    if (!last) continue;
    const kind = isKanji(last.cp) ? isKanji : isLatin(last.cp) ? isLatin : null;
    if (!kind) continue;
    let from = last.at;
    for (let p = before(text, from); p && kind(p.cp); p = before(text, from)) from = p.at;
    if (out.length && from < out[out.length - 1].hide![1]) continue;
    out.push({ from, to: open, rt, hide: [open, open + m[0].length] });
  }
  return out;
}

/** Each token's place in the text, scanning forward; a token not found is skipped. */
export function placeTokens(text: string, tokens: Token[]): { from: number; to: number; token: Token }[] {
  const out: { from: number; to: number; token: Token }[] = [];
  let cursor = 0;
  for (const token of tokens) {
    if (!token.surface) continue;
    const at = text.indexOf(token.surface, cursor);
    if (at < 0) continue;
    cursor = at + token.surface.length;
    out.push({ from: at, to: cursor, token });
  }
  return out;
}

type Seg = { kana: boolean; from: number; to: number; text: string };

function segments(surface: string): Seg[] {
  const segs: Seg[] = [];
  let i = 0;
  for (const c of surface) {
    const kana = isKana(c.codePointAt(0)!);
    const last = segs[segs.length - 1];
    if (last && last.kana === kana) {
      last.to += c.length;
      last.text += c;
    } else segs.push({ kana, from: i, to: i + c.length, text: c });
    i += c.length;
  }
  return segs;
}

/** The reading's share for each non-kana run of `surface` (offsets within it, katakana),
 * using the surface's kana as anchors; one item over the whole surface when they do not match. */
export function alignReading(surface: string, kana: string): { from: number; to: number; rt: string }[] {
  const reading = toKatakana(kana);
  if (!reading || !hasKanji(surface)) return [];
  const whole = [{ from: 0, to: surface.length, rt: reading }];
  const segs = segments(surface);
  const out: { from: number; to: number; rt: string }[] = [];
  let cursor = 0;
  let pending: Seg | null = null;
  for (let s = 0; s < segs.length; s++) {
    const seg = segs[s];
    if (!seg.kana) {
      pending = seg;
      continue;
    }
    const k = toKatakana(seg.text);
    let at: number;
    if (s === segs.length - 1) {
      at = reading.endsWith(k) ? reading.length - k.length : -1;
      if (at < cursor + (pending ? 1 : 0)) return whole;
    } else if (pending) {
      at = reading.indexOf(k, cursor + 1);
    } else {
      at = reading.startsWith(k, cursor) ? cursor : -1;
    }
    if (at < 0) return whole;
    if (pending) {
      out.push({ from: pending.from, to: pending.to, rt: reading.slice(cursor, at) });
      pending = null;
    }
    cursor = at + k.length;
  }
  if (pending) {
    if (cursor >= reading.length) return whole;
    out.push({ from: pending.from, to: pending.to, rt: reading.slice(cursor) });
  }
  return out;
}

const overlaps = (a: number, b: number, c: number, d: number) => a < d && c < b;

function convertAuthor(r: Ruby, mode: ReadingMode): Ruby {
  if (mode === "katakana") return { ...r, rt: toKatakana(r.rt) };
  if (mode === "romaji") return { ...r, rt: toRomaji(r.rt) };
  return { ...r };
}

/** `pos` is the first token's; once a 助動詞 is merged in, the group's final kana is no longer the verb's own. */
type Group = { from: number; to: number; kana: string; pos: string; merged: boolean };

/** The part of speech `toRomaji` should see for the kana of `g` that ends at `end`. */
const romajiPos = (g: Group, end: number): string | undefined =>
  g.pos === "動詞" && (g.merged || end !== g.to) ? undefined : g.pos;

function romajiGroups(text: string, tokens: Token[]): Group[] {
  const groups: Group[] = [];
  for (const { from, to, token } of placeTokens(text, tokens)) {
    if (!token.kana) continue;
    const prev = groups[groups.length - 1];
    if (token.pos === "助動詞" && prev && prev.to === from) {
      prev.to = to;
      prev.kana += token.kana;
      prev.merged = true;
    } else if (isJapanese(token.surface)) {
      groups.push({ from, to, kana: token.kana, pos: token.pos, merged: false });
    }
  }
  return groups;
}

/** Romaji for the parts of `g` outside the author ranges. */
function romajiAround(text: string, g: Group, author: Ruby[]): Ruby[] {
  const cover = author
    .flatMap((a) => [[a.from, a.to, a] as const, ...(a.hide ? [[a.hide[0], a.hide[1], null] as const] : [])])
    .filter(([f, t]) => overlaps(g.from, g.to, f, t))
    .sort((x, y) => x[0] - y[0]);
  if (!cover.length) return [{ from: g.from, to: g.to, rt: toRomaji(g.kana, romajiPos(g, g.to)) }];
  const out: Ruby[] = [];
  const pieces: [number, number][] = [];
  let at = g.from;
  for (const [f, t] of cover) {
    if (f > at) pieces.push([at, f]);
    at = Math.max(at, t);
  }
  if (at < g.to) pieces.push([at, g.to]);
  const kana = toKatakana(g.kana);
  for (const [f, t] of pieces) {
    const piece = text.slice(f, t);
    if (!isJapanese(piece)) continue;
    let rt: string | null = null;
    if (allKana(piece)) rt = piece;
    else if (cover.length === 1 && cover[0][2]) {
      const a = toKatakana(cover[0][2].rt);
      if (f === g.from && t === cover[0][0] && kana.endsWith(a) && kana.length > a.length)
        rt = kana.slice(0, -a.length);
      if (t === g.to && f === cover[0][1] && kana.startsWith(a) && kana.length > a.length)
        rt = kana.slice(a.length);
    }
    if (rt) out.push({ from: f, to: t, rt: toRomaji(rt, romajiPos(g, t)) });
  }
  return out;
}

/** The complete ruby list for the active line: generated readings plus the author rubies,
 * converted to the mode's script, sorted by `from` and never overlapping. `off` → `[]`. */
export function generatedRuby(text: string, tokens: Token[], mode: ReadingMode, author: Ruby[]): Ruby[] {
  if (mode === "off") return [];
  const covered = (f: number, t: number) =>
    author.some((a) => overlaps(f, t, a.from, a.to) || (a.hide && overlaps(f, t, a.hide[0], a.hide[1])));
  const out: Ruby[] = author.map((a) => convertAuthor(a, mode));
  if (mode === "romaji") {
    for (const g of romajiGroups(text, tokens)) out.push(...romajiAround(text, g, author));
  } else {
    const script = mode === "hiragana" ? toHiragana : toKatakana;
    for (const { from, token } of placeTokens(text, tokens)) {
      if (!token.kana) continue;
      for (const p of alignReading(token.surface, token.kana)) {
        const f = from + p.from;
        const t = from + p.to;
        if (!covered(f, t)) out.push({ from: f, to: t, rt: script(p.rt) });
      }
    }
  }
  return out.sort((a, b) => a.from - b.from);
}
