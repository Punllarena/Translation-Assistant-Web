import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

const ITEMS = '[role^="menuitem"]';

/** A button that opens a popover menu. The caller renders the items (buttons with a menuitem role).
 *  On open the checked item (else the first) takes focus; arrow keys move; Escape closes and returns
 *  focus to the button; a press outside closes. */
export default function Menu({ label, buttonLabel, align = "end", children }: {
  label: ReactNode; buttonLabel?: string; align?: "start" | "end"; children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  const items = () => [...(root.current?.querySelectorAll<HTMLElement>(ITEMS) ?? [])];
  useEffect(() => {
    if (!open) return;
    const list = items();
    (list.find((el) => el.getAttribute("aria-checked") === "true") ?? list[0])?.focus();
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!open) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const list = items();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const step = e.key === "ArrowDown" ? 1 : -1;
    const next = at < 0 ? (step > 0 ? 0 : list.length - 1) : (at + step + list.length) % list.length;
    list[next]?.focus();
  };
  return (
    <div className="menu-root" ref={root} onKeyDown={onKeyDown}>
      <button ref={button} type="button" className="quiet" aria-haspopup="menu" aria-expanded={open}
        aria-controls={open ? id : undefined} aria-label={buttonLabel} onClick={() => setOpen((o) => !o)}>
        {label}
      </button>
      {open && <div className={`menu menu-${align}`} role="menu" id={id}>{children(close)}</div>}
    </div>
  );
}
