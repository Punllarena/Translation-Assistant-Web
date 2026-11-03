import type { Entry } from "./mtEvents";

/** One dictionary row as the cards draw it. `pos` is the English tag set (JParser, EDICT codes),
 * `gram` MeCab's Japanese part of speech; a single-backend card fills only one of them. */
export type Row = {
  surface: string; reading?: string; lemma?: string; pos?: string; gram?: string; gloss?: string;
  tense?: string; matched?: boolean; flag?: string;
};

/** How far ahead of MeCab's position a JParser token may sit and still be taken as the same word. */
const LOOKAHEAD = 3;

function lemmaOf(e: Entry): string {
  return [e.lemma, e.base_form].filter((x, i, a) => x && a.indexOf(x) === i && x !== e.surface).join(" / ");
}

/** A single backend's entry as a row (the analysis cards that are not merged). */
export function toRow(e: Entry): Row {
  return { surface: e.surface, reading: e.reading, lemma: lemmaOf(e), pos: e.pos, gloss: e.gloss, tense: e.tense, matched: e.matched };
}

/** MeCab function-word classes, with the EDICT tags that can agree with them. A word MeCab reads as a
 * particle but JParser lists only as a content word is the mismatch worth pointing out; the other
 * classes differ too often by design (an inflected verb listed under its noun form) to flag. */
const FUNCTION_WORDS: Record<string, { name: string; tags: string[] }> = {
  助詞: { name: "a particle", tags: ["prt", "conj", "suf", "cop", "aux", "int"] },
  助動詞: { name: "an auxiliary verb", tags: ["aux", "aux-v", "aux-adj", "cop", "prt", "suf", "v-unspec"] },
};

function disagreement(gram: string | undefined, pos: string | undefined): string | undefined {
  const rule = gram ? FUNCTION_WORDS[gram] : undefined;
  if (!rule || !pos) return undefined;
  const tags = pos.split(",").map((t) => t.trim()).filter(Boolean);
  return tags.length && !tags.some((t) => rule.tags.includes(t)) ? `MeCab reads this as ${rule.name}` : undefined;
}

function join(m: Entry, j: Entry): Row {
  const lemma = lemmaOf(m) || lemmaOf(j);
  return {
    surface: m.surface, reading: m.reading || j.reading, lemma, pos: j.pos, gram: m.pos,
    gloss: j.gloss || m.gloss, tense: j.tense || m.tense, matched: j.matched ?? m.matched,
    flag: disagreement(m.pos, j.pos),
  };
}

/** One row per word, in MeCab's order (it splits the sentence); each takes the next JParser entry with
 * the same surface, if one sits within the lookahead. A word only one backend produced keeps its own
 * fields, and with MeCab not yet in the result (`mecab` empty) the JParser entries show as they are. */
export function mergeEntries(mecab: Entry[], jparser: Entry[]): Row[] {
  const rows: Row[] = [];
  let at = 0;
  for (const m of mecab) {
    let hit = -1;
    for (let k = at; k < Math.min(jparser.length, at + LOOKAHEAD + 1); k++) {
      if (jparser[k].surface === m.surface) { hit = k; break; }
    }
    if (hit < 0) {
      rows.push({ ...toRow(m), pos: undefined, gram: m.pos });
      continue;
    }
    for (; at < hit; at++) rows.push(toRow(jparser[at]));
    rows.push(join(m, jparser[hit]));
    at = hit + 1;
  }
  for (; at < jparser.length; at++) rows.push(toRow(jparser[at]));
  return rows;
}
