import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";
import { invalidateLibrary } from "../library/queries";
import { shownTitle, type Doc } from "../library/shelf";
import { browserZone } from "../time";
import IllustrationsPublish from "./IllustrationsPublish";
import PublishDialog, { type PublishMode } from "./PublishDialog";
import { statusTone } from "./label";
import { WP_TAG_LABEL, wpTag, wpTagTone } from "./wpTag";

const LIVE_LABEL: Record<string, string> = {
  publish: "Published", future: "Scheduled", draft: "Draft", "": "Not on WordPress",
};

const local = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** The chapter table's WordPress tag (spec §2). The tag is a button: it opens a popover that
 *  asks WordPress for the live status, shows the stored date and offers the matching publish
 *  flow — Reschedule for a scheduled chapter, Update post for a published one. */
export default function WpTagButton({ doc }: { doc: Doc }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<{ top: number; right: number } | null>(null);
  const [dialog, setDialog] = useState<PublishMode | "illustrations" | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const tag = wpTag(doc, new Date());
  const stored = doc.wp_scheduled_for ?? doc.wp_published_at;
  const status = useQuery({
    queryKey: ["wp", "status", doc.id], enabled: open, retry: false, gcTime: 0,
    refetchOnWindowFocus: false,
    queryFn: () => call(api.POST("/documents/{document_id}/wp/status", {
      params: { path: { document_id: doc.id }, query: { tz: browserZone() } },
    })),
  });
  useEffect(() => {
    if (status.dataUpdatedAt > 0) void invalidateLibrary(queryClient);
  }, [status.dataUpdatedAt, queryClient]);
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    popover.current?.focus();
    const press = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!popover.current?.contains(target) && !button.current?.contains(target)) close();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", press);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", press);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  const show = () => {
    const rect = button.current?.getBoundingClientRect();
    if (rect) setAt({ top: rect.bottom + 6, right: Math.max(8, window.innerWidth - rect.right) });
    setOpen(true);
  };
  // An Illustrations chapter's own publish has no date, so it never offers Reschedule.
  const mode: PublishMode =
    !doc.is_illustrations && tag === "scheduled" ? "reschedule"
    : tag === "published" || tag === "due" ? "update"
    : "publish";
  const action = doc.is_illustrations
    ? tag === "none" ? "Publish…" : "Update post…"
    : mode === "reschedule" ? "Reschedule…"
    : mode === "update" ? "Update post…"
    : "Publish…";
  const live = status.data?.status;
  const postUrl = status.data?.post_url || doc.wp_post_url;
  const run = () => {
    setOpen(false);
    setDialog(doc.is_illustrations ? "illustrations" : mode);
  };
  return (
    <>
      <button ref={button} type="button" className={`badge wp-tag ${wpTagTone(tag)}`.trim()}
        aria-haspopup="dialog" aria-expanded={open} aria-label={`WordPress: ${WP_TAG_LABEL[tag]}`}
        onClick={() => (open ? close() : show())}>{WP_TAG_LABEL[tag]}</button>
      {open && at && (
        <div ref={popover} tabIndex={-1} role="dialog" aria-label={`WordPress status for ${shownTitle(doc)}`}
          className="wp-pop" style={{ top: at.top, right: at.right }}>
          <p className="wp-pop-title">{shownTitle(doc)}</p>
          <p>
            On WordPress:{" "}
            {status.isPending ? <span className="muted">checking…</span>
              : status.isError ? <span className="error">{status.error.message}</span>
              : <span className={`badge ${statusTone(live ?? "")}`}>{LIVE_LABEL[live ?? ""] ?? live}</span>}
          </p>
          {status.data?.remote_error && <p className="error" role="alert">{status.data.remote_error}</p>}
          {status.isSuccess && !status.data.remote_error && <p className="muted">Checked just now.</p>}
          {stored && (
            <p className="muted">
              {doc.wp_status === "future" && live === "publish"
                ? `Scheduled for ${local(stored)}, now live.`
                : `${doc.wp_status === "future" ? "Scheduled for" : "Published"} ${local(stored)}`}
            </p>
          )}
          {postUrl && <p><a href={postUrl} target="_blank" rel="noreferrer">Open the post</a></p>}
          <button type="button" className="small primary" onClick={run}>{action}</button>
        </div>
      )}
      {dialog === "illustrations" && <IllustrationsPublish doc={doc} onClose={() => setDialog(null)} />}
      {dialog !== null && dialog !== "illustrations" && (
        <PublishDialog doc={doc} mode={dialog} onClose={() => setDialog(null)} />
      )}
    </>
  );
}
