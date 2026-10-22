import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, call, type Schemas } from "../../api/client";
import JobProgress from "../../jobs/JobProgress";
import type { Job } from "../../jobs/follow";
import { invalidateLibrary } from "../queries";
import { EMPTY_FIELDS, seriesBody, type SeriesFieldsValue } from "./fields";
import SeriesFields from "./SeriesFields";

type Novel = Schemas["NovelInfo"];

export default function NewFromSyosetu() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [novel, setNovel] = useState<Novel | null>(null);
  const [value, setValue] = useState<SeriesFieldsValue>(EMPTY_FIELDS);
  const [started, setStarted] = useState<{ seriesId: number; jobId: number } | null>(null);
  const read = useMutation({
    mutationFn: () => call(api.POST("/scrape/syosetu/novel", { body: { url: url.trim() } })),
    onSuccess: (n) => {
      setNovel(n);
      setValue((v) => ({ ...v, originalTitle: n.title, originalAuthor: n.author }));
    },
  });
  const create = useMutation({
    mutationFn: async () => {
      const s = await call(api.POST("/series", { body: { ...seriesBody(value), syosetu_url: url.trim() } }));
      await invalidateLibrary(queryClient);
      try {
        const job = await call(api.POST("/series/{series_id}/syosetu/fetch", {
          params: { path: { series_id: s.id } }, body: { nums: [(novel as Novel).first_chapter.num] },
        }));
        setStarted({ seriesId: s.id, jobId: job.id });
      } catch {
        navigate(`/series/${s.id}?tab=tools`); // the series exists: fetch from its Tools tab
      }
    },
  });
  const onDone = (job: Job) => {
    const id = (job.result as { document_ids?: number[] } | null)?.document_ids?.[0];
    void invalidateLibrary(queryClient);
    const seriesId = (started as { seriesId: number }).seriesId;
    navigate(job.state === "done" && id ? `/documents/${id}` : `/series/${seriesId}?tab=tools`);
  };
  const changeUrl = (u: string) => {
    setUrl(u);
    setNovel(null);
    read.reset();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!novel) {
      if (url.trim() && !read.isPending) read.mutate();
    } else if (value.title.trim() && !create.isPending) create.mutate();
  };
  const busy = create.isPending || started !== null;
  const first = novel?.first_chapter;
  return (
    <form className="panel pad" onSubmit={submit}>
      <h2 className="sec">Syosetu</h2>
      <p className="muted">Start from a syosetu URL and fetch the first chapter.</p>
      <label className="field"><span>Syosetu URL</span>
        <input type="url" value={url} disabled={busy} onChange={(e) => changeUrl(e.target.value)} />
      </label>
      {!novel && (
        <div className="row-fields">
          <button type="submit" disabled={!url.trim() || read.isPending}>Read</button>
        </div>
      )}
      {read.error && <p className="error" role="alert">{read.error.message}</p>}
      {novel && first && (
        <>
          <SeriesFields value={value} onChange={setValue} disabled={busy} />
          <p className="muted">
            {novel.short_story
              ? `Short story: ${first.title} will be fetched as one chapter.`
              : `Chapter ${first.num}: ${first.title} will be fetched.`}
          </p>
          {create.error && <p className="error" role="alert">{create.error.message}</p>}
          {started ? (
            <JobProgress jobId={started.jobId} background={false} onDone={onDone} />
          ) : (
            <div className="row-fields">
              <button type="submit" className="primary" disabled={value.title.trim() === "" || busy}>Create</button>
            </div>
          )}
        </>
      )}
    </form>
  );
}
