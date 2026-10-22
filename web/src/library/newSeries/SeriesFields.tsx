import type { SeriesFieldsValue } from "./fields";

export default function SeriesFields({ value, onChange, disabled }: {
  value: SeriesFieldsValue; onChange: (v: SeriesFieldsValue) => void; disabled?: boolean;
}) {
  const set = (patch: Partial<SeriesFieldsValue>) => onChange({ ...value, ...patch });
  return (
    <>
      <label className="field"><span>Title</span>
        <input value={value.title} required maxLength={300} disabled={disabled}
          onChange={(e) => set({ title: e.target.value })} />
      </label>
      <label className="field"><span>Japanese title</span>
        <input value={value.originalTitle} maxLength={300} disabled={disabled}
          onChange={(e) => set({ originalTitle: e.target.value })} />
      </label>
      <label className="field"><span>Author</span>
        <input value={value.originalAuthor} maxLength={300} disabled={disabled}
          onChange={(e) => set({ originalAuthor: e.target.value })} />
      </label>
      <label className="field"><span>Author (romaji)</span>
        <input value={value.authorRomaji} maxLength={300} disabled={disabled}
          onChange={(e) => set({ authorRomaji: e.target.value })} />
      </label>
    </>
  );
}
