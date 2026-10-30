import type { ReactNode } from "react";
import { Link } from "react-router";
import { wpBadge } from "../publish/badge";
import { statusTone } from "../publish/label";
import { chapterNumber, type VolumeGroup } from "./volumeGroups";
import { COLUMNS, type ColumnId } from "./chapterColumns";
import { shownTitle, type Doc } from "./shelf";

/** What a cell renders from: the chapter, its volume group and the table's state. */
export interface CellCtx {
  doc: Doc;
  group: VolumeGroup;
  syosetu: boolean;
  /** Select mode: the title is text, not a link (a row click toggles it). */
  selecting: boolean;
  /** Chapter ids a queued Ollama item covers. */
  queued: Set<number>;
}

const WP_LABEL: Record<string, string> = { publish: "Published", future: "Scheduled" };

/** The column's CSS class; the title has none, so it takes the leftover width. */
const CLASS: Partial<Record<ColumnId, string>> = { progress: "ch-prog", wp: "ch-wp", wp_date: "ch-wpdate" };
export const cellClass = (id: ColumnId) => CLASS[id] ?? `ch-${id}`;

const date = (iso: string) => new Date(iso).toLocaleDateString();
const dateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });

function content(id: ColumnId, { doc, group, syosetu, selecting, queued }: CellCtx): ReactNode {
  switch (id) {
    case "num":
      return chapterNumber(group, doc, syosetu) ?? "";
    case "title":
      return selecting
        ? shownTitle(doc)
        : <Link className="row-link" to={`/documents/${doc.id}`} aria-label={`Open ${shownTitle(doc)}`}>{shownTitle(doc)}</Link>;
    case "progress":
      return `${doc.progress}%`;
    case "edited":
      return date(doc.updated_at);
    case "wp":
      return (
        <span className={`badge ${statusTone(doc.wp_status)}`} title={wpBadge(doc) || undefined}>
          {WP_LABEL[doc.wp_status] ?? "Not posted"}
        </span>
      );
    case "original":
      return doc.chapter_title && doc.chapter_title !== doc.title ? doc.title : "";
    case "images":
      return doc.image_count;
    case "lines":
      return doc.line_count;
    case "translated":
      return `${doc.translated_count} / ${doc.line_count}`;
    case "chars":
      return doc.char_count;
    case "words":
      return doc.word_count;
    case "wp_date": {
      const at = doc.wp_scheduled_for ?? doc.wp_published_at;
      return at ? dateTime(at) : "";
    }
    case "ollama":
      return doc.ollama_waiting > 0 ? `${doc.ollama_waiting} waiting` : queued.has(doc.id) ? "Queued" : "";
    case "source":
      return doc.source_url
        ? <a href={doc.source_url} target="_blank" rel="noreferrer">syosetu</a>
        : "";
    case "added":
      return date(doc.created_at);
  }
}

/** One cell of the chapter table for a chosen column. */
export function cell(id: ColumnId, ctx: CellCtx): ReactNode {
  const cls = id === "progress" && ctx.doc.progress >= 100 ? "ch-prog ok" : cellClass(id);
  return (
    <td key={id} className={cls} title={id === "title" ? shownTitle(ctx.doc) : undefined}>
      {content(id, ctx)}
    </td>
  );
}

/** The header cell text per column. */
export const HEADERS = Object.fromEntries(COLUMNS.map((c) => [c.id, c.label])) as Record<ColumnId, string>;
