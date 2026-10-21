import { useId } from "react";

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

/** Kind (with suggestions), decimal number and subtitle of a volume's name. */
export default function VolumeNameFields({ value, onChange, kinds, autoFocus }: {
  value: VolumeName; onChange: (v: VolumeName) => void; kinds: string[]; autoFocus?: boolean;
}) {
  const listId = useId();
  return (
    <div className="row-fields">
      <label className="field"><span>Kind</span>
        <input list={listId} value={value.kind} maxLength={40} autoFocus={autoFocus}
          onChange={(e) => onChange({ ...value, kind: e.target.value })} />
        <datalist id={listId}>{kinds.map((k) => <option key={k} value={k} />)}</datalist>
      </label>
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
