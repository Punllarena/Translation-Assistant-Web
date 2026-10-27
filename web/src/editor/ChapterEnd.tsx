import { useQuery } from "@tanstack/react-query";
import { useState, type MouseEvent } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { shownTitle, type Doc } from "../library/shelf";
import IllustrationsPublish from "../publish/IllustrationsPublish";
import PublishDialog from "../publish/PublishDialog";

/** The card after the last line: where to go next, and publish. Every move goes through `onLeave`.
 *  `doc` is undefined until the documents list has loaded. */
export default function ChapterEnd({ doc, next, seriesId, total, done, words, firstLeft, onJump, onLeave }: {
  doc: Doc | undefined;
  next: Doc | null;
  seriesId: number;
  total: number;
  done: number;
  words: number;
  firstLeft: number | null;
  onJump: (i: number) => void;
  onLeave: (to: string) => void;
}) {
  const [publishing, setPublishing] = useState(false);
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const setUp = Boolean(creds.data?.find((c) => c.kind === "wordpress" && c.name === "")?.endpoint_url);
  const left = total - done;
  const finished = left <= 0 || firstLeft == null;
  const nextTo = next ? `/documents/${next.id}` : null;
  const plural = (k: number) => (k === 1 ? "line" : "lines");
  // A plain left click leaves through onLeave; modified and non-primary clicks keep the link's own behaviour.
  const link = (to: string, text: string, primary: boolean) => (
    <Link className={primary ? "btn primary" : "btn"} to={to} onClick={(e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onLeave(to);
    }}>{text}</Link>
  );
  return (
    <section className="chapter-end" aria-label="End of chapter">
      {total > 0 && (
        <p className="chapter-end-status">
          {finished ? `All ${total} ${plural(total)} translated · ${words} words` : `${left} ${plural(left)} left`}
        </p>
      )}
      {doc && !next && <p className="muted">Last chapter of the series</p>}
      <div className="chapter-end-actions">
        {!finished && firstLeft != null && (
          <button type="button" className="primary" onClick={() => onJump(firstLeft)}>Jump to line {firstLeft + 1}</button>
        )}
        {next && nextTo && link(nextTo, `Next chapter → ${next.chapter_number != null ? `${next.chapter_number} · ` : ""}${shownTitle(next)}`, finished)}
        {setUp && doc && <button type="button" onClick={() => setPublishing(true)}>Publish to WordPress</button>}
        {link(`/series/${seriesId}`, "Back to series", false)}
      </div>
      {publishing && doc && (doc.is_illustrations
        ? <IllustrationsPublish doc={doc} onClose={() => setPublishing(false)} />
        : <PublishDialog doc={doc} onClose={() => setPublishing(false)} />)}
    </section>
  );
}
