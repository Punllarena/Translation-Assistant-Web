import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, ApiError, call } from "../api/client";
import IllustrationsPublish from "../publish/IllustrationsPublish";
import PublishDialog from "../publish/PublishDialog";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import MoveDialog from "./MoveDialog";
import { useFlushOllama, useQueueOllama } from "./useOllamaQueue";
import { shownTitle, titleField, type Doc } from "./shelf";
import { invalidateLibrary } from "./queries";

type Open = null | "rename" | "refetch" | "publish" | "move" | "delete" | "flush";

/** A chapter row's ⋯ menu and the dialogs its items open. */
export default function ChapterMenu({ doc }: { doc: Doc }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const [conflict, setConflict] = useState<string | null>(null); // the re-fetch 409, asking to force
  const [error, setError] = useState<string | null>(null); // Illustrations-mark failures
  const id = { params: { path: { document_id: doc.id } } };
  const changed = () => invalidateLibrary(queryClient);
  const closeAll = () => { setOpen(null); setConflict(null); };
  const title = shownTitle(doc);
  const rename = useMutation({
    mutationFn: (t: string) => call(api.PATCH("/documents/{document_id}", { ...id, body: { [titleField(doc)]: t } })),
    onSuccess: async () => { await changed(); closeAll(); },
  });
  const refetch = useMutation({
    mutationFn: async (force: boolean) => {
      try {
        await call(api.POST("/documents/{document_id}/refetch", { ...id, body: { force } }));
        return true;
      } catch (e) {
        if (force || !(e instanceof ApiError) || e.status !== 409) throw e;
        setConflict(e.message);
        return false;
      }
    },
    onSuccess: async (finished) => {
      if (!finished) return;
      await changed();
      closeAll();
    },
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/documents/{document_id}", id)),
    onSuccess: async () => { await changed(); closeAll(); },
  });
  const mark = useMutation({
    mutationFn: (is_illustrations: boolean) =>
      call(api.PATCH("/documents/{document_id}", { ...id, body: { is_illustrations } })),
    onMutate: () => setError(null),
    onError: (e) => setError(e.message),
    onSettled: changed,
  });
  const ollama = useQueueOllama();
  const flush = useFlushOllama(() => closeAll());
  const exportUrl = (format: string) => `/api/documents/${doc.id}/export?format=${format}`;
  const item = (label: string, act: () => void, close: () => void, className?: string) => (
    <button type="button" role="menuitem" className={className} onClick={() => { close(); act(); }}>{label}</button>
  );
  return (
    <>
      <Menu label="⋯" buttonLabel={`Actions for ${title}`}>
        {(close) => (
          <>
            <Link role="menuitem" className="btn" to={`/documents/${doc.id}`}>Open</Link>
            {item("Rename…", () => { rename.reset(); setOpen("rename"); }, close)}
            <a role="menuitem" className="btn" href={exportUrl("txt")} download onClick={close}>Export TXT</a>
            <a role="menuitem" className="btn" href={exportUrl("md")} download onClick={close}>Export Markdown</a>
            <a role="menuitem" className="btn" href={exportUrl("md-ruby")} download onClick={close}>Export Ruby Markdown</a>
            {doc.source_url && item("Re-fetch…", () => { refetch.reset(); setOpen("refetch"); }, close)}
            {item("Queue for Ollama", () => ollama.queue({ kind: "documents", series_id: doc.series_id, document_ids: [doc.id] }), close)}
            {item("Flush Ollama output…", () => { flush.reset(); setOpen("flush"); }, close)}
            {item("Publish…", () => setOpen("publish"), close)}
            {doc.is_illustrations
              ? item("Unmark Illustrations", () => mark.mutate(false), close)
              : doc.line_count === 0 && item("Mark as Illustrations", () => mark.mutate(true), close)}
            <Link role="menuitem" className="btn" to={`/documents/${doc.id}/split`}>Split…</Link>
            {item("Move to…", () => setOpen("move"), close)}
            {item("Delete", () => { remove.reset(); setOpen("delete"); }, close, "danger")}
          </>
        )}
      </Menu>
      {error && <span className="error" role="alert">{error}</span>}
      {ollama.error && <span className="error" role="alert">{ollama.error}</span>}
      {ollama.note && <span className="muted" role="status">{ollama.note}</span>}
      {open === "flush" && (
        <ConfirmDialog title="Flush Ollama output" confirmLabel="Flush" danger busy={flush.pending}
          message={`Clear Ollama's saved suggestions for "${title}"? Your own translation is not touched.`}
          error={flush.error} onConfirm={() => flush.flush({ document_ids: [doc.id] })} onClose={closeAll} />
      )}
      {open === "rename" && (
        <PromptDialog title="Rename chapter" label="Title" initial={title} confirmLabel="Rename"
          note={title !== doc.title && <>Original title: <span lang={doc.source_language}>{doc.title}</span></>}
          busy={rename.isPending} error={rename.error?.message} onClose={closeAll}
          onSubmit={(t) => (t.trim() === title ? closeAll() : rename.mutate(t.trim()))} />
      )}
      {open === "refetch" && (conflict === null ? (
        <ConfirmDialog title="Re-fetch chapter" confirmLabel="Re-fetch" busy={refetch.isPending}
          message={`Re-fetch content from: ${doc.source_url}? Existing translations will be preserved by line position.`}
          error={refetch.error?.message} onConfirm={() => refetch.mutate(false)} onClose={closeAll} />
      ) : (
        <ConfirmDialog title="Replace anyway?" confirmLabel="Replace anyway" danger busy={refetch.isPending}
          message={conflict} error={refetch.error?.message} onConfirm={() => refetch.mutate(true)} onClose={closeAll} />
      ))}
      {open === "publish" && (doc.is_illustrations
        ? <IllustrationsPublish doc={doc} onClose={closeAll} />
        : <PublishDialog doc={doc} onClose={closeAll} />)}
      {open === "move" && <MoveDialog ids={[doc.id]} currentSeriesId={doc.series_id} currentVolumeId={doc.volume_id} onClose={closeAll} />}
      {open === "delete" && (
        <ConfirmDialog title="Delete chapter" confirmLabel="Delete" danger busy={remove.isPending}
          message={`Delete "${title}"? This can't be undone.`} error={remove.error?.message}
          onConfirm={() => remove.mutate()} onClose={closeAll} />
      )}
    </>
  );
}
