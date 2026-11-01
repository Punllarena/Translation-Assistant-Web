import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

const ITEMS = '[role^="menuitem"]';

/** Move focus to the next or previous item in the menu under `root`, wrapping. Shared by the
 *  popover menu and the spell menu, so both answer the arrow keys the same way. */
export function moveMenuFocus(e: { key: string; preventDefault(): void }, root: HTMLElement | null): void {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const list = [...(root?.querySelectorAll<HTMLElement>(ITEMS) ?? [])];
  const at = list.indexOf(document.activeElement as HTMLElement);
  const step = e.key === "ArrowDown" ? 1 : -1;
  const next = at < 0 ? (step > 0 ? 0 : list.length - 1) : (at + step + list.length) % list.length;
  list[next]?.focus();
}

/** A button that opens a popover menu. The caller renders the items (buttons with a menuitem role).
 *  On open the checked item (else the first) takes focus; arrow keys move; Escape closes and returns
 *  focus to the button; a press outside closes. */
export default function Menu({ label, buttonLabel, align = "end", onPointerDown, children }: {
  label: ReactNode; buttonLabel?: string; align?: "start" | "end";
  /** Captures the moment the trigger button is pressed, before focus/selection moves. */
  onPointerDown?: () => void;
  children: (close: () => void) => ReactNode;
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
    moveMenuFocus(e, root.current);
  };
  return (
    <div className="menu-root" ref={root} onKeyDown={onKeyDown}>
      <button ref={button} type="button" className="quiet" aria-haspopup="menu" aria-expanded={open}
        aria-controls={open ? id : undefined} aria-label={buttonLabel} onClick={() => setOpen((o) => !o)}
        onPointerDown={onPointerDown}>
        {label}
      </button>
      {open && <div className={`menu menu-${align}`} role="menu" id={id}>{children(close)}</div>}
    </div>
  );
}
