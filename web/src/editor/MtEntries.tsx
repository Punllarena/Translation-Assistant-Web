import type { Row } from "./mtMerge";

const POS_WORDS: Record<string, string> = {
  n: "noun", pn: "pronoun", conj: "conjunction", pref: "prefix", prt: "particle", suf: "suffix",
  v1: "verb (ichidan)", v5: "verb (godan)", vt: "transitive", vi: "intransitive", vs: "suru verb",
  "adj-i": "i-adjective", "adj-na": "na-adjective", adv: "adverb", int: "interjection", ctr: "counter", exp: "expression",
};
const KANA_ONLY = /^[぀-ヿー]+$/;

function EntryRow({ e }: { e: Row }) {
  const reading = e.reading && !KANA_ONLY.test(e.surface) ? e.reading : "";
  const pos = e.pos?.split(",").map((t) => POS_WORDS[t.trim()] ?? t.trim()).join(", ");
  const noMatch = e.matched === false && !e.gloss;
  return (
    <li className={e.matched === false ? "muted" : undefined}>
      <span className="mt-surface" lang="ja">{e.surface}</span>
      {reading && <span className="mt-reading" lang="ja"><span aria-hidden>【</span>{reading}<span aria-hidden>】</span></span>}
      {e.lemma && <span className="mt-lemma" lang="ja"><span aria-hidden>← </span>{e.lemma}</span>}
      {e.gram && <span className="mt-gram" lang="ja">{e.gram}</span>}
      {(pos || e.tense || e.gloss || noMatch) && (
        <span className="mt-gloss">
          {pos && <span className="mt-pos" title={e.pos} lang={/[^ -~]/.test(pos) ? "ja" : undefined}>{pos}</span>}
          {e.tense && <span className="mt-pos">{e.tense}</span>}
          {noMatch ? <span className="mt-nomatch">no entry</span> : e.gloss}
        </span>
      )}
      {e.flag && <span className="mt-flag">{e.flag}</span>}
    </li>
  );
}

/** The dictionary rows of an analysis card (JParser, MeCab or the two merged). */
export default function Entries({ rows }: { rows: Row[] }) {
  if (!rows.length) return null;
  return <ul className="mt-entries">{rows.map((r, i) => <EntryRow key={i} e={r} />)}</ul>;
}
