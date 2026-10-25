import { useEffect, useId, useRef, useState } from "react";
import {
  DEFAULT_DIR, DEFAULT_FILTERS, SORT_LABEL, SOURCE_LABEL, STATUS_LABEL, activeGroups,
  type LibraryFilters, type LibrarySort, type SortKey,
} from "./libraryQuery";

const SORT_KEYS = Object.keys(SORT_LABEL) as SortKey[];
const SOURCES = Object.keys(SOURCE_LABEL) as LibraryFilters["sources"];
const STATUSES = Object.keys(STATUS_LABEL) as LibraryFilters["statuses"];
const WORDPRESS: [LibraryFilters["wordpress"], string][] = [["any", "Any"], ["published", "Has published"], ["none", "None published"]];
const ARCHIVED: [LibraryFilters["archived"], string][] = [["hide", "Hide"], ["include", "Include"], ["only", "Only archived"]];

export function SortControl({ sort, onChange }: { sort: LibrarySort; onChange(s: LibrarySort): void }) {
  return (
    <div className="sort-control">
      <select aria-label="Sort by" value={sort.key}
        onChange={(e) => { const key = e.target.value as SortKey; onChange({ key, dir: DEFAULT_DIR[key] }); }}>
        {SORT_KEYS.map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
      </select>
      <button type="button" aria-label="Reverse order" title={sort.dir === "desc" ? "Descending" : "Ascending"}
        onClick={() => onChange({ key: sort.key, dir: sort.dir === "desc" ? "asc" : "desc" })}>
        {sort.dir === "desc" ? "↓" : "↑"}
      </button>
    </div>
  );
}

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function FiltersButton({ filters, onChange }: { filters: LibraryFilters; onChange(f: LibraryFilters): void }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const name = useId();
  const n = activeGroups(filters);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [open]);

  return (
    <div className="filters" ref={wrap}>
      <button type="button" ref={button} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        Filters{n > 0 ? ` (${n})` : ""}
      </button>
      {open && (
        <div className="filters-panel" id={panelId} role="group" aria-label="Library filters">
          <fieldset>
            <legend>Source</legend>
            {SOURCES.map((s) => (
              <label key={s}><input type="checkbox" checked={filters.sources.includes(s)}
                onChange={() => onChange({ ...filters, sources: toggle(filters.sources, s) })} /> {SOURCE_LABEL[s]}</label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Status</legend>
            {STATUSES.map((s) => (
              <label key={s}><input type="checkbox" checked={filters.statuses.includes(s)}
                onChange={() => onChange({ ...filters, statuses: toggle(filters.statuses, s) })} /> {STATUS_LABEL[s]}</label>
            ))}
          </fieldset>
          <fieldset>
            <legend>WordPress</legend>
            {WORDPRESS.map(([v, label]) => (
              <label key={v}><input type="radio" name={`${name}-wp`} checked={filters.wordpress === v}
                onChange={() => onChange({ ...filters, wordpress: v })} /> {label}</label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Archived</legend>
            {ARCHIVED.map(([v, label]) => (
              <label key={v}><input type="radio" name={`${name}-ar`} checked={filters.archived === v}
                onChange={() => onChange({ ...filters, archived: v })} /> {label}</label>
            ))}
          </fieldset>
        </div>
      )}
    </div>
  );
}

export function FilterChips({ filters, onChange, shown, total }: {
  filters: LibraryFilters; onChange(f: LibraryFilters): void; shown: number; total: number;
}) {
  const chips: { group: string; text: string; clear: Partial<LibraryFilters> }[] = [];
  if (filters.sources.length > 0) {
    chips.push({ group: "Source", text: filters.sources.map((s) => SOURCE_LABEL[s]).join(", "), clear: { sources: [] } });
  }
  if (filters.statuses.length > 0) {
    chips.push({ group: "Status", text: filters.statuses.map((s) => STATUS_LABEL[s]).join(", "), clear: { statuses: [] } });
  }
  if (filters.wordpress !== DEFAULT_FILTERS.wordpress) {
    chips.push({ group: "WordPress", text: WORDPRESS.find(([v]) => v === filters.wordpress)![1], clear: { wordpress: DEFAULT_FILTERS.wordpress } });
  }
  if (filters.archived !== DEFAULT_FILTERS.archived) {
    chips.push({ group: "Archived", text: ARCHIVED.find(([v]) => v === filters.archived)![1], clear: { archived: DEFAULT_FILTERS.archived } });
  }
  return (
    <div className="filter-chips">
      {chips.map((c) => (
        <span key={c.group} className="filter-chip">
          {c.group}: {c.text}
          <button type="button" className="icon" aria-label={`Remove ${c.group} filter`}
            onClick={() => onChange({ ...filters, ...c.clear })}>✕</button>
        </span>
      ))}
      {chips.length > 0 && (
        <button type="button" className="quiet small" onClick={() => onChange(DEFAULT_FILTERS)}>Clear all</button>
      )}
      <span className="muted filter-count">{shown} of {total} series</span>
    </div>
  );
}
