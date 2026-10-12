import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import { invalidateLibrary } from "./queries";

/** Pick chapters from the series' Syosetu index and fetch them as a background job. */
export default function SyosetuFetch({ seriesId }: { seriesId: number }) {
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
    onSuccess: (chapters) => setPicked(new Set(chapters.filter((c) => !c.fetched).map((c) => c.num))),
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
  const toggle = (num: number, on: boolean) =>
    setPicked((p) => { const n = new Set(p); if (on) n.add(num); else n.delete(num); return n; });
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
          {list.data && (
            <>
              <ul>
                {list.data.map((c) => (
                  <li key={c.num}>
                    <label>
                      <input type="checkbox" disabled={c.fetched} checked={!c.fetched && picked.has(c.num)}
                        onChange={(e) => toggle(c.num, e.target.checked)} />{" "}
                      Chapter {c.num}: {c.title}{c.fetched ? " (already fetched)" : ""}
                    </label>
                  </li>
                ))}
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
