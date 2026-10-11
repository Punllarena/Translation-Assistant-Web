import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError, call } from "../api/client";
import Editor from "./Editor";

export default function EditorPage() {
  const id = Number(useParams().id);
  const [profileId, setProfileId] = useState<number | null>(null);
  const mountedAt = useRef(Date.now());
  // Never seed the editor from a cached copy: saves do not update it, so reopening a chapter
  // would show (and then overwrite) old translations.
  const doc = useQuery({
    queryKey: ["document", id, "lines", profileId],
    queryFn: () =>
      call(api.GET("/documents/{document_id}/lines", {
        params: { path: { document_id: id }, query: profileId === null ? {} : { profile_id: profileId } },
      })),
    placeholderData: keepPreviousData,
    gcTime: 0,
    refetchOnMount: "always",
  });
  const gone = doc.error instanceof ApiError && doc.error.status === 404;
  useEffect(() => {
    // A deleted chapter must not keep being the sign-in landing page.
    if (gone) void call(api.DELETE("/settings/{key}", { params: { path: { key: "last_document_id" } } })).catch(() => {});
  }, [gone]);
  if (doc.isError) {
    return <main><p className="error" role="alert">{doc.error.message}</p><Link to="/">Back to the library</Link></main>;
  }
  if (doc.isPending || (!doc.isPlaceholderData && doc.dataUpdatedAt < mountedAt.current)) return <main><p className="muted">Loading…</p></main>;
  return <Editor key={id} id={id} data={doc.data} onProfile={setProfileId} />;
}
