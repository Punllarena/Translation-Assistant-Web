import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

/** A native modal <dialog>: opened with showModal() on mount; Escape or cancel calls onClose. */
function Modal({ title, onClose, onSubmit, children }: {
  title: string; onClose: () => void; onSubmit?: (e: FormEvent) => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  return (
    <dialog ref={ref} aria-label={title} onCancel={(e) => { e.preventDefault(); onClose(); }}>
      {onSubmit ? <form onSubmit={onSubmit}>{children}</form> : children}
    </dialog>
  );
}

export function ConfirmDialog(p: {
  title: string; message: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean;
  error?: string | null; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal title={p.title} onClose={p.onClose}>
      <div className="dlg-head"><h2>{p.title}</h2></div>
      <div className="dlg-body">
        <div>{p.message}</div>
        {p.error && <p className="error" role="alert">{p.error}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" onClick={p.onClose}>Cancel</button>
        <button type="button" className={p.danger ? "primary danger" : "primary"} disabled={p.busy}
          onClick={p.onConfirm}>{p.confirmLabel}</button>
      </div>
    </Modal>
  );
}

export function PromptDialog(p: {
  title: string; label: string; initial?: string; confirmLabel: string; busy?: boolean;
  error?: string | null; onSubmit: (value: string) => void; onClose: () => void;
}) {
  const [value, setValue] = useState(p.initial ?? "");
  const empty = value.trim() === "";
  return (
    <Modal title={p.title} onClose={p.onClose} onSubmit={(e) => {
      e.preventDefault();
      if (!empty && !p.busy) p.onSubmit(value);
    }}>
      <div className="dlg-head"><h2>{p.title}</h2></div>
      <div className="dlg-body">
        <label className="field">
          <span>{p.label}</span>
          <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        {p.error && <p className="error" role="alert">{p.error}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" onClick={p.onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={empty || p.busy}>{p.confirmLabel}</button>
      </div>
    </Modal>
  );
}
