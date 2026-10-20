import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, ApiError, call, errorMessage } from "../api/client";
import PublishDialog from "../publish/PublishDialog";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import MoveDialog from "./MoveDialog";
import type { Doc } from "./shelf";
import { invalidateLibrary } from "./queries";

type Open = null | "rename" | "refetch" | "publish" | "move" | "delete";

/** A chapter row's ⋯ menu and the dialogs its items open. */
export default function ChapterMenu({ doc }: { doc: Doc }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const [conflict, setConflict] = useState<string | null>(null); // the re-fetch 409, asking to force
  const [coverError, setCoverError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const id = { params: { path: { document_id: doc.id } } };
  const changed = () => invalidateLibrary(queryClient);
  const closeAll = () => { setOpen(null); setConflict(null); };
  const rename = useMutation({
    mutationFn: (title: string) => call(api.PATCH("/documents/{document_id}", { ...id, body: { title } })),
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
  const cover = useMutation({
    mutationFn: async (picked: File | null) => {
      if (!picked) return call(api.DELETE("/documents/{document_id}/cover", id));
      const form = new FormData();
      form.append("file", picked);
      const response = await fetch(`/api/documents/${doc.id}/cover`, { method: "PUT", body: form });
      if (!response.ok) {
        throw new ApiError(
          response.status,
          response.status === 413 ? "File too large" : errorMessage(await response.json().catch(() => null)),
        );
      }
    },
    onMutate: () => setCoverError(null),
    onError: (e) => setCoverError(e.message),
    onSettled: changed,
  });
  const exportUrl = (format: string) => `/api/documents/${doc.id}/export?format=${format}`;
  const item = (label: string, act: () => void, close: () => void, className?: string) => (
    <button type="button" role="menuitem" className={className} onClick={() => { close(); act(); }}>{label}</button>
  );
  return (
    <>
      <Menu label="⋯" buttonLabel={`Actions for ${doc.title}`}>
        {(close) => (
          <>
            <Link role="menuitem" className="btn" to={`/documents/${doc.id}`}>Open</Link>
            {item("Rename…", () => { rename.reset(); setOpen("rename"); }, close)}
            <a role="menuitem" className="btn" href={exportUrl("txt")} download onClick={close}>Export TXT</a>
            <a role="menuitem" className="btn" href={exportUrl("md")} download onClick={close}>Export Markdown</a>
            <a role="menuitem" className="btn" href={exportUrl("md-ruby")} download onClick={close}>Export Ruby Markdown</a>
            {doc.source_url && item("Re-fetch…", () => { refetch.reset(); setOpen("refetch"); }, close)}
            {item("Publish…", () => setOpen("publish"), close)}
            {item("Set cover…", () => file.current?.click(), close)}
            {doc.has_cover && item("Clear cover", () => cover.mutate(null), close)}
            <Link role="menuitem" className="btn" to={`/documents/${doc.id}/split`}>Split…</Link>
            {item("Move to…", () => setOpen("move"), close)}
            {item("Delete", () => { remove.reset(); setOpen("delete"); }, close, "danger")}
          </>
        )}
      </Menu>
      <input ref={file} type="file" hidden accept="image/png,image/jpeg,image/gif,image/webp"
        aria-label={`Cover for ${doc.title}`} onChange={(e) => {
          const picked = e.target.files?.[0];
          e.target.value = "";
          if (picked) cover.mutate(picked);
        }} />
      {coverError && <span className="error" role="alert">{coverError}</span>}
      {open === "rename" && (
        <PromptDialog title="Rename chapter" label="Title" initial={doc.title} confirmLabel="Rename"
          busy={rename.isPending} error={rename.error?.message} onClose={closeAll}
          onSubmit={(t) => (t.trim() === doc.title ? closeAll() : rename.mutate(t.trim()))} />
      )}
      {open === "refetch" && (conflict === null ? (
        <ConfirmDialog title="Re-fetch chapter" confirmLabel="Re-fetch" busy={refetch.isPending}
          message={`Re-fetch content from: ${doc.source_url}? Existing translations will be preserved by line position.`}
          error={refetch.error?.message} onConfirm={() => refetch.mutate(false)} onClose={closeAll} />
      ) : (
        <ConfirmDialog title="Replace anyway?" confirmLabel="Replace anyway" danger busy={refetch.isPending}
          message={conflict} error={refetch.error?.message} onConfirm={() => refetch.mutate(true)} onClose={closeAll} />
      ))}
      {open === "publish" && <PublishDialog doc={doc} onClose={closeAll} />}
      {open === "move" && <MoveDialog ids={[doc.id]} currentSeriesId={doc.series_id} onClose={closeAll} />}
      {open === "delete" && (
        <ConfirmDialog title="Delete chapter" confirmLabel="Delete" danger busy={remove.isPending}
          message={`Delete "${doc.title}"? This can't be undone.`} error={remove.error?.message}
          onConfirm={() => remove.mutate()} onClose={closeAll} />
      )}
    </>
  );
}
