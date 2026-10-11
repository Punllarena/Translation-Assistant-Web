import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, call } from "../api/client";
import Editor from "./Editor";

export default function EditorPage() {
  const id = Number(useParams().id);
  const [profileId, setProfileId] = useState<number | null>(null);
  const doc = useQuery({
    queryKey: ["document", id, "lines", profileId],
    queryFn: () =>
      call(api.GET("/documents/{document_id}/lines", {
        params: { path: { document_id: id }, query: profileId === null ? {} : { profile_id: profileId } },
      })),
    placeholderData: keepPreviousData,
  });
  if (doc.isPending) return <main><p className="muted">Loading…</p></main>;
  if (doc.isError) {
    return <main><p className="error" role="alert">{doc.error.message}</p><Link to="/">Back to the library</Link></main>;
  }
  return <Editor key={id} id={id} data={doc.data} onProfile={setProfileId} />;
}
