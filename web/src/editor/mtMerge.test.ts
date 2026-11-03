import { describe, expect, it } from "vitest";
import type { Entry } from "./mtEvents";
import { mergeEntries, toRow } from "./mtMerge";

const mecab: Entry[] = [
  { surface: "その", reading: "ソノ", lemma: "其の", pos: "連体詞", gloss: "that; the" },
  { surface: "頷き", reading: "ウナズキ", lemma: "頷く", pos: "動詞", gloss: "to nod" },
  { surface: "に", reading: "ニ", pos: "助詞", gloss: "load; baggage" },
];
const jparser: Entry[] = [
  { surface: "その", reading: "その", pos: "n", gloss: "garden; orchard" },
  { surface: "頷き", reading: "うなずき", pos: "n", gloss: "nod; inclination of the head" },
  { surface: "に", reading: "に", pos: "n", gloss: "load; baggage" },
];

describe("merging MeCab and JParser", () => {
  it("makes one row per MeCab token with JParser's meaning and MeCab's reading and grammar", () => {
    const rows = mergeEntries(mecab, jparser);
    expect(rows).toHaveLength(3);
    expect(rows[1]).toMatchObject({
      surface: "頷き", reading: "ウナズキ", lemma: "頷く", pos: "n", gram: "動詞", gloss: "nod; inclination of the head",
    });
  });

  it("flags a function word MeCab sees that JParser lists only as a noun", () => {
    const rows = mergeEntries(mecab, jparser);
    expect(rows[2].flag).toBe("MeCab reads this as a particle");
    expect(rows[0].flag).toBeUndefined();
    expect(rows[1].flag).toBeUndefined();
  });

  it("does not flag when JParser's tags include a particle", () => {
    const rows = mergeEntries(
      [{ surface: "ながら", pos: "助詞" }],
      [{ surface: "ながら", pos: "conj,pref,prt", gloss: "while" }],
    );
    expect(rows[0].flag).toBeUndefined();
  });

  it("keeps a word only one backend produced", () => {
    const rows = mergeEntries(
      [{ surface: "A", pos: "名詞", gloss: "a" }, { surface: "B", pos: "名詞" }],
      [{ surface: "A", gloss: "ay" }, { surface: "X", gloss: "ex" }],
    );
    expect(rows.map((r) => r.surface)).toEqual(["A", "B", "X"]);
    expect(rows[1]).toMatchObject({ gram: "名詞", pos: undefined });
  });

  it("puts JParser words that MeCab skipped before the next shared word", () => {
    const rows = mergeEntries(
      [{ surface: "C" }],
      [{ surface: "A" }, { surface: "B" }, { surface: "C", gloss: "see" }],
    );
    expect(rows.map((r) => r.surface)).toEqual(["A", "B", "C"]);
    expect(rows[2].gloss).toBe("see");
  });

  it("shows JParser alone while MeCab has not answered, and MeCab alone the other way", () => {
    expect(mergeEntries([], jparser).map((r) => r.surface)).toEqual(["その", "頷き", "に"]);
    expect(mergeEntries(mecab, [])[0]).toMatchObject({ surface: "その", gram: "連体詞", gloss: "that; the" });
  });

  it("marks a row unmatched only when both sides agree there is no entry", () => {
    const rows = mergeEntries([{ surface: "Z" }], [{ surface: "Z", matched: false }]);
    expect(rows[0].matched).toBe(false);
  });

  it("builds a plain row from a single backend entry, dropping a lemma equal to the surface", () => {
    expect(toRow({ surface: "猫", lemma: "猫", base_form: "猫", pos: "n" })).toMatchObject({ lemma: "", pos: "n" });
  });
});
