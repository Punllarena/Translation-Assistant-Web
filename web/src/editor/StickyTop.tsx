import { useEffect, useRef, type ReactNode } from "react";

/** The status and find bars, stuck as one block. Their height changes as they wrap, so it is
 *  published on the page as --top-h for what sticks below them. */
export default function StickyTop({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => el.parentElement?.style.setProperty("--top-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return <div className="editor-top" ref={ref}>{children}</div>;
}
