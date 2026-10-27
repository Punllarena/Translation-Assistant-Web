import { useState, type FormEvent } from "react";
import { Modal } from "../ui/Dialog";
import { DAY_NAMES, validZone, type ScheduleValue } from "./schedule";
import { defaultSchedule } from "./useSchedule";

/** Edit the Ollama night window: times, days (the local day it starts on) and the time zone. */
export default function ScheduleEditor({ initial, busy, error, onSave, onClose }: {
  initial: ScheduleValue | undefined; busy: boolean; error: string | null;
  onSave: (value: ScheduleValue) => void; onClose: () => void;
}) {
  const [s, setS] = useState<ScheduleValue>(initial ?? defaultSchedule());
  const toggle = (d: number) =>
    setS({ ...s, days: s.days.includes(d) ? s.days.filter((x) => x !== d) : [...s.days, d].sort((a, b) => a - b) });
  const zoneOk = validZone(s.tz);
  const valid = /^\d{2}:\d{2}$/.test(s.start) && /^\d{2}:\d{2}$/.test(s.end) && zoneOk;
  const submit = (e: FormEvent) => { e.preventDefault(); if (valid && !busy) onSave({ ...s, tz: s.tz.trim() }); };
  return (
    <Modal title="Ollama schedule" onClose={onClose} busy={busy} onSubmit={submit}>
      <div className="dlg-head">
        <h2>Ollama schedule</h2>
        <p className="muted">The queue runs by itself inside this window. An end time before the start runs past midnight.</p>
      </div>
      <div className="dlg-body">
        <label className="check"><input type="checkbox" checked={s.enabled} onChange={(e) => setS({ ...s, enabled: e.target.checked })} /> Run on a schedule</label>
        <div className="sched-times">
          <label className="field"><span>Start</span>
            <input type="time" required value={s.start} onChange={(e) => setS({ ...s, start: e.target.value })} /></label>
          <label className="field"><span>End</span>
            <input type="time" required value={s.end} onChange={(e) => setS({ ...s, end: e.target.value })} /></label>
        </div>
        <fieldset className="sched-days">
          <legend className="label">Days the window starts on</legend>
          {DAY_NAMES.map((name, d) => (
            <label key={name} className="check"><input type="checkbox" checked={s.days.includes(d)} onChange={() => toggle(d)} /> {name}</label>
          ))}
        </fieldset>
        <label className="field"><span>Time zone</span>
          <input value={s.tz} aria-invalid={!zoneOk} onChange={(e) => setS({ ...s, tz: e.target.value })} />
          {zoneOk
            ? <span className="hint">An IANA name such as Asia/Manila.</span>
            : <span className="error" role="alert">Unknown time zone. Use an IANA name such as Asia/Manila.</span>}</label>
        {error && <p className="error" role="alert">{error}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={busy} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={busy || !valid}>Save</button>
      </div>
    </Modal>
  );
}
