import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";

const ITEMS = '[role^="menuitem"]';
const GAP = 6; // between the trigger and the popover
const MARGIN = 8; // kept clear at the viewport's edges
const MIN_ROOM = 80; // below/above room the flipped menu may use

/** A button that opens a popover menu. The caller renders the items (buttons with a menuitem role).
 *  On open the checked item (else the first) takes focus; arrow keys move; Escape closes and returns
 *  focus to the button; a press outside closes. With `fixed` the popover is placed from the trigger's
 *  rect instead of being absolutely positioned: a scrolling table wrapper would otherwise clip it. */
export default function Menu({ label, buttonLabel, align = "end", fixed = false, onPointerDown, children }: {
  label: ReactNode; buttonLabel?: string; align?: "start" | "end";
  /** Place the popover with `position: fixed` inside the viewport, flipping above the trigger when
   *  there is no room below; it closes on window scroll and resize. */
  fixed?: boolean;
  /** Captures the moment the trigger button is pressed, before focus/selection moves. */
  onPointerDown?: () => void;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<CSSProperties>();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
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
  useLayoutEffect(() => {
    if (!open || !fixed) return;
    const trigger = button.current?.getBoundingClientRect();
    const el = pop.current;
    if (!trigger || !el) return;
    const height = el.offsetHeight;
    const width = el.offsetWidth;
    const below = window.innerHeight - trigger.bottom - GAP - MARGIN;
    const above = trigger.top - GAP - MARGIN;
    // Flip only when the menu fits better above; otherwise scroll inside the room below.
    const flip = height > below && above > below;
    const room = Math.max(flip ? above : below, MIN_ROOM);
    const wanted = align === "end" ? trigger.right - width : trigger.left;
    const left = Math.min(Math.max(MARGIN, wanted), window.innerWidth - width - MARGIN);
    setPlace({
      top: flip ? trigger.top - GAP - Math.min(height, room) : trigger.bottom + GAP,
      left: Math.max(MARGIN, left),
      maxHeight: room,
      overflowY: height > room ? "auto" : undefined,
    });
    const dismiss = () => setOpen(false);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [open, fixed, align]);
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
        aria-controls={open ? id : undefined} aria-label={buttonLabel} onClick={() => setOpen((o) => !o)}
        onPointerDown={onPointerDown}>
        {label}
      </button>
      {open && (
        <div ref={pop} className={`menu menu-${align}${fixed ? " menu-fixed" : ""}`} role="menu" id={id}
          style={fixed ? place : undefined}>{children(close)}</div>
      )}
    </div>
  );
}
