/**
 * Volume naming rules: kind + decimal index + subtitle.
 *
 * Twin of `api/core/volume_names.py`; both are checked against the same case
 * table, `volumeNames.cases.json`. Indexes stay strings end to end, so "2.50"
 * is never rounded through a float.
 */

export const DEFAULT_TEMPLATE = "{series} - {kind} {index} - {subtitle}";
const PLACEHOLDERS = ["series", "kind", "index", "subtitle"];

export interface NameParts {
  series: string;
  kind: string;
  index: string | null;
  subtitle: string;
}

export interface ParsedName {
  kind: string;
  index: string | null;
  subtitle: string;
}

const placeholderRe = () => /\{([^{}]*)\}/g;

/** "" for null; trailing zeros and a bare point are dropped ("3.500" -> "3.5"). */
export function formatIndex(index: string | null): string {
  if (index === null) return "";
  const s = index.trim();
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/** null for a valid template, else a message naming the bad placeholder or brace. */
export function templateError(template: string): string | null {
  for (const m of template.matchAll(placeholderRe())) {
    if (!PLACEHOLDERS.includes(m[1])) return `unknown placeholder {${m[1]}}`;
  }
  const stray = template.replace(placeholderRe(), "");
  for (const ch of "{}") {
    if (stray.includes(ch)) return `stray brace '${ch}' in template`;
  }
  return null;
}

export function render(template: string, v: NameParts, sep = " - "): string {
  const values: Record<string, string> = {
    series: v.series,
    kind: v.kind,
    index: formatIndex(v.index),
    subtitle: v.subtitle,
  };
  // Split on the literal separator first so a separator inside a value
  // (a subtitle like "Re:Start - Part 1") is never split.
  const parts: string[] = [];
  for (const segment of template.split(sep)) {
    const names = [...segment.matchAll(placeholderRe())].map((m) => m[1]);
    if (names.length && !names.some((n) => values[n])) continue;
    const text = segment
      .replace(placeholderRe(), (_, n: string) => values[n] ?? "")
      .replace(/\s+/g, " ")
      .trim();
    if (text) parts.push(text);
  }
  return parts.join(sep);
}

/** Display label, e.g. "Side Story 1 · Roxy". */
export function label(kind: string, index: string | null, subtitle: string): string {
  return render("{kind} {index} · {subtitle}", { series: "", kind, index, subtitle }, " · ");
}

/** Same as label() with a plain " - " separator, for WordPress. */
export function wpLabel(kind: string, index: string | null, subtitle: string): string {
  return render("{kind} {index} - {subtitle}", { series: "", kind, index, subtitle });
}

const NUM = String.raw`(\d+(?:\.\d+)?)`;
// The number must end the string or be followed by whitespace or a separator,
// so "3rd Arc" is not volume 3.
const END = String.raw`(?=$|[\s\-–—:.])`;
const shape = (head: string, flags = "") => new RegExp(String.raw`^${head}` + NUM + END, flags);
const SHAPES: [string, RegExp][] = [
  ["Volume", shape(String.raw`(?:volume|vol\.?|v)\s*`, "i")],
  ["Volume", new RegExp(String.raw`^第\s*${NUM}\s*巻`)],
  ["Side Story", shape(String.raw`(?:side story|ss)\s*`, "i")],
  ["Short Stories", shape(String.raw`short stories\s*`, "i")],
  ["Volume", shape("")],
];
const SEP_LEAD = /^\s*[-–—:.]?\s*/;

function stripSeries(text: string, series: string): string {
  const s = series.normalize("NFKC").trim();
  if (!s || !text.toLowerCase().startsWith(s.toLowerCase())) return text;
  const rest = text.slice(s.length);
  for (const lead of [" - ", ":", " "]) {
    if (rest.startsWith(lead)) return rest.slice(lead.length).trim() || text;
  }
  return text;
}

/** Split a legacy single-string volume title into kind, index and subtitle. */
export function parseTitle(title: string, seriesTitle = ""): ParsedName {
  const text = stripSeries(title.normalize("NFKC").trim(), seriesTitle);
  for (const [kind, rx] of SHAPES) {
    const m = rx.exec(text);
    if (!m) continue;
    const rest = text.slice(m[0].length).replace(SEP_LEAD, "").trim();
    const index = formatIndex(m[1].replace(/^0+(?=\d)/, ""));
    return { kind, index, subtitle: rest };
  }
  return { kind: "", index: null, subtitle: title.trim() };
}

/** The next free Volume number: the highest Volume index, floored, plus one. */
export function nextVolumeIndex(
  volumes: { kind: string; volume_index: string | null }[],
): string {
  let top = 0;
  for (const v of volumes) {
    if (v.volume_index === null || v.kind.trim().toLowerCase() !== "volume") continue;
    top = Math.max(top, Number(v.volume_index.split(".")[0]) || 0);
  }
  return String(top + 1);
}
