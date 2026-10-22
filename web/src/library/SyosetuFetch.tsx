import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import HeadingVolumes from "./HeadingVolumes";
import { invalidateLibrary } from "./queries";
import type { SeriesRow } from "./shelf";
import { groupRuns } from "./syosetuGroups";

const shortStory = (chapters: { fetched: boolean; url: string }[], series: SeriesRow) =>
  chapters.length === 1 && chapters[0].fetched && chapters[0].url === series.syosetu_url;

/** Pick chapters from the series' Syosetu index and fetch them as a background job. */
export default function SyosetuFetch({ series }: { series: SeriesRow }) {
  const seriesId = series.id;
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const active = useQuery({
    queryKey: ["jobs", "active", seriesId],
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true, series_id: seriesId } } })),
  });
  const list = useMutation({
    mutationFn: () => call(api.GET("/series/{series_id}/syosetu/chapters", { params: { path: { series_id: seriesId } } })),
    onSuccess: (data) => setPicked(new Set(data.chapters.filter((c) => !c.fetched).map((c) => c.num))),
  });
  const fetchSelected = useMutation({
    mutationFn: () => call(api.POST("/series/{series_id}/syosetu/fetch", {
      params: { path: { series_id: seriesId } }, body: { nums: [...picked].sort((a, b) => a - b) },
    })),
    onSuccess: (job) => { setFinished(false); setJobId(job.id); },
  });
  const running = jobId ?? active.data?.find((j) => j.kind === "syosetu_fetch")?.id ?? null;
  const fetchMore = () => {
    setJobId(null);
    setFinished(false);
    list.reset();
    queryClient.removeQueries({ queryKey: ["jobs", "active", seriesId] });
  };
  const toggle = (nums: number[], on: boolean) =>
    setPicked((p) => { const n = new Set(p); for (const num of nums) { if (on) n.add(num); else n.delete(num); } return n; });
  type Chapter = NonNullable<typeof list.data>["chapters"][number];
  const row = (c: Chapter) => (
    <li key={c.num}>
      <label>
        <input type="checkbox" disabled={c.fetched} checked={!c.fetched && picked.has(c.num)}
          onChange={(e) => toggle([c.num], e.target.checked)} />{" "}
        Chapter {c.num}: {c.title}{c.fetched ? " (already fetched)" : ""}
      </label>
    </li>
  );
  return (
    <section className="stack">
      <h2>Fetch from Syosetu</h2>
      {running !== null ? (
        <>
          <JobProgress jobId={running} onDone={() => { setFinished(true); void invalidateLibrary(queryClient); }} />
          {finished && <div className="toolbar"><button type="button" onClick={fetchMore}>Fetch more</button></div>}
        </>
      ) : (
        <>
          <div className="toolbar">
            <button type="button" disabled={list.isPending} onClick={() => list.mutate()}>Load chapter list</button>
          </div>
          {list.isError && <p className="error" role="alert">{list.error.message}</p>}
          {list.data && shortStory(list.data.chapters, series) && (
            <p className="muted">This is a short story; there are no more chapters to fetch.</p>
          )}
          {list.data && !shortStory(list.data.chapters, series) && (
            <>
              {list.data.chapters.some((c) => c.group) && <HeadingVolumes series={series} markers={list.data.markers} />}
              <ul>
                {groupRuns(list.data.chapters).map((run, i) => {
                  if (run.group === null) return run.chapters.map(row);
                  const open = run.chapters.filter((c) => !c.fetched).map((c) => c.num);
                  const on = open.filter((n) => picked.has(n)).length;
                  return (
                    <li key={`g${i}`}>
                      <label>
                        <input type="checkbox" disabled={open.length === 0}
                          checked={open.length > 0 && on === open.length}
                          ref={(el) => { if (el) el.indeterminate = on > 0 && on < open.length; }}
                          onChange={(e) => toggle(open, e.target.checked)} />{" "}
                        <strong>{run.group}</strong>
                      </label>
                      <ul>{run.chapters.map(row)}</ul>
                    </li>
                  );
                })}
              </ul>
              <div className="toolbar">
                <button type="button" disabled={picked.size === 0 || fetchSelected.isPending}
                  onClick={() => fetchSelected.mutate()}>Fetch selected ({picked.size})</button>
              </div>
              {fetchSelected.isError && <p className="error" role="alert">{fetchSelected.error.message}</p>}
            </>
          )}
        </>
      )}
    </section>
  );
}
