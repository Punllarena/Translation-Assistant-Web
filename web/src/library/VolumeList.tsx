import { useState, type DragEvent } from "react";
import type { VolumeGroup, VolumeKey } from "./volumeGroups";

/** The drag payload a chapter row carries: its document id. */
export const CHAPTER_MIME = "application/x-ta-chapter";

export const groupTitle = (g: VolumeGroup) => g.volume?.title ?? "No volume";

export function VolumeCover({ group }: { group: VolumeGroup }) {
  return group.coverImageId != null
    ? <img className="cover" src={`/api/images/${group.coverImageId}`} alt="" loading="lazy" />
    : <span className="cover cover-tile" aria-hidden="true">{groupTitle(group)}</span>;
}

export function Progress({ value }: { value: number }) {
  return (
    <span className="prog" role="progressbar" aria-label="Translated" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={value}><i style={{ width: `${value}%` }} /></span>
  );
}

const carriesChapter = (e: DragEvent) => e.dataTransfer.types.includes(CHAPTER_MIME);

function VolumeInfo({ group }: { group: VolumeGroup }) {
  return (
    <>
      <VolumeCover group={group} />
      <span className="vol-info">
        <span className="vol-title">{groupTitle(group)}</span>
        <span className="muted vol-count">{group.docs.length} {group.docs.length === 1 ? "chapter" : "chapters"}</span>
        <Progress value={group.progress} />
      </span>
    </>
  );
}

/** The left pane: one entry per volume (and "No volume"), each a drop target for chapter rows.
 *  In select mode volumes get checkboxes (shift-click ticks a range) and nothing is a drop target. */
export default function VolumeList({ groups, selected, onSelect, onNewVolume, onDropChapter,
  selecting, picked, onToggleSelecting, onPick, onMerge }: {
  groups: VolumeGroup[]; selected: VolumeKey | null; onSelect: (key: VolumeKey) => void;
  onNewVolume: () => void; onDropChapter: (docId: number, key: VolumeKey) => void;
  selecting: boolean; picked: Set<number>; onToggleSelecting: () => void;
  onPick: (id: number, shift: boolean) => void; onMerge: () => void;
}) {
  const [over, setOver] = useState<VolumeKey | null>(null);
  return (
    <nav className="vol-list" aria-label="Volumes">
      <div className="vol-list-head">
        <button type="button" onClick={onToggleSelecting}>{selecting ? "Done" : "Select"}</button>
      </div>
      {selecting && picked.size >= 2 && (
        <div className="vol-merge-bar">
          <button type="button" className="primary" onClick={onMerge}>Merge {picked.size} volumes</button>
        </div>
      )}
      <ul>
        {groups.map((g) => selecting ? (
          <li key={g.key}>
            {g.volume ? (
              <label className={picked.has(g.volume.id) ? "vol-item picking picked" : "vol-item picking"}>
                <input type="checkbox" checked={picked.has(g.volume.id)} onChange={() => {}}
                  onClick={(e) => onPick(g.volume!.id, e.shiftKey)} />
                <VolumeInfo group={g} />
              </label>
            ) : (
              <div className="vol-item picking"><VolumeInfo group={g} /></div>
            )}
          </li>
        ) : (
          <li key={g.key}>
            <button type="button" className={over === g.key ? "vol-item drop" : "vol-item"}
              aria-current={g.key === selected ? "true" : undefined} onClick={() => onSelect(g.key)}
              onDragOver={(e) => {
                if (!carriesChapter(e)) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                setOver(g.key);
              }}
              onDragLeave={() => setOver((k) => (k === g.key ? null : k))}
              onDrop={(e) => {
                setOver(null);
                const id = Number(e.dataTransfer.getData(CHAPTER_MIME));
                if (!id) return;
                e.preventDefault();
                onDropChapter(id, g.key);
              }}>
              <VolumeInfo group={g} />
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="vol-add" onClick={onNewVolume}><span aria-hidden="true">+</span> New volume</button>
    </nav>
  );
}
