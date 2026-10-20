import type { SeriesRow } from "./shelf";

export type Choice = { id: string; title: string };

/** An existing series, or a new series title; setting one clears the other (both is a 422). */
export default function SeriesChoice({ series, value, onChange }: {
  series: SeriesRow[]; value: Choice; onChange: (c: Choice) => void;
}) {
  return (
    <div className="row-fields">
      <label className="field"><span>Series</span>
        <select value={value.id} onChange={(e) => onChange({ id: e.target.value, title: "" })}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
      <label className="field"><span>New series title</span>
        <input value={value.title} onChange={(e) => onChange({ id: "", title: e.target.value })} />
      </label>
    </div>
  );
}

/** Form fields for whichever of the two is set. */
export function appendSeries(form: FormData, c: Choice) {
  if (c.id) form.append("series_id", c.id);
  else if (c.title.trim()) form.append("series_title", c.title.trim());
}
