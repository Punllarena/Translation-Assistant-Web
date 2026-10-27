import { nextStart, summary } from "./schedule";
import { useSchedule } from "./useSchedule";

/** What runs by itself: the Ollama window (switchable) and the nightly clean-up (read-only). */
export default function ScheduledTab() {
  const { schedule, save, loading, error } = useSchedule();
  const next = nextStart(schedule, new Date());
  return (
    <section className="sec" aria-label="Scheduled jobs">
      <ul className="job-list panel">
        <li>
          <span className="job-main">
            <strong>Ollama translation</strong>
            <span className="hint">{schedule ? summary({ ...schedule, enabled: true }) : "No window set. Add one under Ollama queue."}</span>
            {schedule?.enabled && next && <span className="hint">Next window opens {next.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</span>}
          </span>
          <label className="check">
            <input type="checkbox" role="switch" checked={schedule?.enabled ?? false} disabled={!schedule || loading || save.isPending}
              onChange={(e) => schedule && save.mutate({ ...schedule, enabled: e.target.checked })} />
            {schedule?.enabled ? "On" : "Off"}
          </label>
        </li>
        <li>
          <span className="job-main">
            <strong>Ollama clean-up</strong>
            <span className="hint">Runs once a day on its own when suggestions are being held. Not adjustable.</span>
          </span>
        </li>
      </ul>
      {(save.error ?? error) && <p className="error" role="alert">{(save.error ?? error)!.message}</p>}
    </section>
  );
}
