import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { moveItem } from "../library/order";
import { ConfirmDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import AddToQueueDialog, { QUEUE_KEY } from "./AddToQueueDialog";
import { formatDuration } from "./eta";
import { ACTIVE_JOBS_KEY } from "./RunningJobs";
import ScheduleEditor from "./ScheduleEditor";
import { nextStart, summary } from "./schedule";
import { useSchedule } from "./useSchedule";

const MIME = "application/x-ta-queue-item";

/** The Ollama queue tab: the night window, the ordered queue (drag a grip or use the arrows), Add, Run now, Flush. */
export default function OllamaQueue() {
  const queryClient = useQueryClient();
  const { schedule, save, error: settingsError } = useSchedule();
  const queue = useQuery({ queryKey: QUEUE_KEY, queryFn: () => call(api.GET("/ollama/queue")), refetchInterval: 10_000 });
  const [dialog, setDialog] = useState<null | "schedule" | "add" | "flush">(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const items = queue.data ?? [];
  const refresh = () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY });
  const reorder = useMutation({
    mutationFn: (ids: number[]) => call(api.PUT("/ollama/queue/order", { body: { ids } })),
    onSuccess: (data) => queryClient.setQueryData(QUEUE_KEY, data),
    onError: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => call(api.DELETE("/ollama/queue/{item_id}", { params: { path: { item_id: id } } })),
    onSettled: refresh,
  });
  const run = useMutation({
    mutationFn: () => call(api.POST("/ollama/run")),
    onSuccess: () => { setNotice("Run started."); void queryClient.invalidateQueries({ queryKey: ACTIVE_JOBS_KEY }); },
    onError: () => setNotice(null),
  });
  const flush = useMutation({
    mutationFn: () => call(api.POST("/ollama/flush", { body: {} })),
    onSuccess: (r) => {
      setNotice(`Cleared ${r.cleared.toLocaleString()} held ${r.cleared === 1 ? "suggestion" : "suggestions"}.`);
      setDialog(null);
    },
  });
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = moveItem(items, from, to);
    queryClient.setQueryData(QUEUE_KEY, next);
    reorder.mutate(next.map((i) => i.id));
  };
  const next = nextStart(schedule, new Date());
  const total = items.reduce((n, i) => n + (i.estimate_seconds ?? 0), 0);
  const failure = run.error ?? queue.error ?? reorder.error ?? remove.error ?? settingsError;
  return (
    <section className="sec" aria-label="Ollama queue">
      <div className="panel pad queue-schedule">
        <div>
          <span className="label">Schedule</span>
          <p>{summary(schedule)}</p>
          {next && <p className="hint">Next window opens {next.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</p>}
        </div>
        <button type="button" onClick={() => setDialog("schedule")}>Edit</button>
      </div>
      <div className="queue-bar">
        <button type="button" onClick={() => setDialog("add")}>Add</button>
        <button type="button" className="primary" disabled={run.isPending || items.length === 0} onClick={() => run.mutate()}>Run now</button>
        <button type="button" className="danger" onClick={() => setDialog("flush")}>Flush everything</button>
        {total > 0 && <span className="hint">About {formatDuration(total * 1000)} of work</span>}
      </div>
      {notice && <p className="muted" role="status">{notice}</p>}
      {failure && <p className="error" role="alert">{failure.message}</p>}
      {queue.isPending ? <p className="muted">Loading…</p> : items.length === 0 ? (
        <p className="muted">Nothing is queued. Add a series, a volume or some chapters.</p>
      ) : (
        <ol className="queue-list panel">
          {items.map((item, i) => (
            <li key={item.id} className={[over === item.id ? "drop" : "", dragging === item.id ? "dragging" : ""].join(" ").trim() || undefined}
              onDragOver={(e) => { if (!e.dataTransfer.types.includes(MIME)) return; e.preventDefault(); setOver(item.id); }}
              onDragLeave={() => setOver((o) => (o === item.id ? null : o))}
              onDrop={(e) => {
                setOver(null);
                const from = items.findIndex((x) => x.id === Number(e.dataTransfer.getData(MIME)));
                if (from < 0) return;
                e.preventDefault();
                setDragging(null);
                move(from, i);
              }}>
              <span className="grip" draggable title="Drag to reorder" aria-hidden="true"
                onDragStart={(e) => {
                  e.dataTransfer.setData(MIME, String(item.id));
                  e.dataTransfer.effectAllowed = "move";
                  setTimeout(() => setDragging(item.id)); // Chrome cancels a drag re-rendered inside dragstart
                }}
                onDragEnd={() => { setDragging(null); setOver(null); }}>⠿</span>
              <span className="queue-main">
                <strong>{item.label}</strong>
                <span className="hint">
                  {item.kind === "series" ? "Whole series" : item.kind === "volume" ? `${item.series_title} · volume` : item.series_title}
                  {" · "}{item.lines_left.toLocaleString()} {item.lines_left === 1 ? "line" : "lines"} left
                  {item.estimate_seconds != null && ` · about ${formatDuration(item.estimate_seconds * 1000)}`}
                </span>
              </span>
              <span className="queue-move">
                <button type="button" className="quiet" aria-label={`Move ${item.label} up`} disabled={i === 0} onClick={() => move(i, i - 1)}>↑</button>
                <button type="button" className="quiet" aria-label={`Move ${item.label} down`} disabled={i === items.length - 1} onClick={() => move(i, i + 1)}>↓</button>
              </span>
              <Menu label="⋯" buttonLabel={`Actions for ${item.label}`}>
                {(close) => (
                  <button type="button" role="menuitem" className="danger" onClick={() => { close(); remove.mutate(item.id); }}>Remove</button>
                )}
              </Menu>
            </li>
          ))}
        </ol>
      )}
      {dialog === "schedule" && (
        <ScheduleEditor initial={schedule} busy={save.isPending} error={save.error?.message ?? null}
          onSave={(v) => save.mutate(v, { onSuccess: () => setDialog(null) })} onClose={() => { save.reset(); setDialog(null); }} />
      )}
      {dialog === "add" && <AddToQueueDialog onClose={() => setDialog(null)} />}
      {dialog === "flush" && (
        <ConfirmDialog title="Flush everything" danger confirmLabel="Flush everything" busy={flush.isPending}
          message="Delete every held Ollama suggestion, with its reasoning and prompt. Your statistics are kept, and queued items stay queued."
          error={flush.error?.message} onConfirm={() => flush.mutate()} onClose={() => { flush.reset(); setDialog(null); }} />
      )}
    </section>
  );
}
