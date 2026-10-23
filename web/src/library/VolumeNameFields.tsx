import { useId, useState } from "react";

export interface VolumeName {
  kind: string;
  index: string;
  subtitle: string;
}

const STANDARD_KINDS = ["Volume", "Side Story", "Short Stories", "Extra"];

/** The standard kinds plus the series' own distinct kinds, without repeats. */
export function kindOptions(volumes: { kind: string }[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const k of [...STANDARD_KINDS, ...volumes.map((v) => v.kind.trim())]) {
    if (k && !seen.has(k.toLowerCase())) {
      seen.add(k.toLowerCase());
      out.push(k);
    }
  }
  return out;
}

/** The option in kinds that a kind picks ("" for none), or null when it needs Other. */
export function listedKind(kind: string, kinds: string[]): string | null {
  const folded = kind.trim().toLowerCase();
  if (!folded) return "";
  return kinds.find((k) => k.toLowerCase() === folded) ?? null;
}

const OTHER = "\u0000other";

/** Kind (a list with Other), decimal number and subtitle of a volume's name. */
export default function VolumeNameFields({ value, onChange, kinds, autoFocus }: {
  value: VolumeName; onChange: (v: VolumeName) => void; kinds: string[]; autoFocus?: boolean;
}) {
  const selectId = useId();
  const [picked, setPicked] = useState(false);
  const listed = listedKind(value.kind, kinds);
  const other = picked || listed === null;
  const pick = (choice: string) => {
    setPicked(choice === OTHER);
    onChange({ ...value, kind: choice === OTHER ? "" : choice });
  };
  return (
    <div className="row-fields">
      <div className="field"><label htmlFor={selectId}>Kind</label>
        <div className="kind-pick">
          <select id={selectId} value={other ? OTHER : listed} autoFocus={autoFocus}
            onChange={(e) => pick(e.target.value)}>
            {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
            <option value="">No kind</option>
            <option value={OTHER}>Other…</option>
          </select>
          {other && (
            <input aria-label="Other kind" value={value.kind} maxLength={40} autoFocus={picked}
              placeholder="e.g. Arc" onChange={(e) => onChange({ ...value, kind: e.target.value })} />
          )}
        </div>
      </div>
      <label className="field"><span>Number</span>
        <input inputMode="decimal" pattern={String.raw`\d+(\.\d{1,3})?`} title="A number such as 3 or 3.5"
          value={value.index} onChange={(e) => onChange({ ...value, index: e.target.value.trim() })} />
      </label>
      <label className="field"><span>Subtitle</span>
        <input value={value.subtitle} maxLength={300} onChange={(e) => onChange({ ...value, subtitle: e.target.value })} />
      </label>
    </div>
  );
}
