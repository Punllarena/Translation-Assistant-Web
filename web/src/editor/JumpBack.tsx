import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp } from "../ui/icons";

type Where = "above" | "below" | "visible";

/** Where the card of line `index` is relative to the viewport (null while unknown). */
function useWhere(index: number | null): Where | null {
  const [where, setWhere] = useState<Where | null>(null);
  useEffect(() => {
    setWhere(null);
    if (index == null) return;
    const el = document.querySelector(`article[data-index="${index}"]`);
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      const e = entries[entries.length - 1];
      setWhere(e.isIntersecting ? "visible" : e.boundingClientRect.top < 0 ? "above" : "below");
    });
    io.observe(el);
    return () => io.disconnect();
  }, [index]);
  return where;
}

/** Floating buttons that bring the next untranslated line or the card being edited back into view. */
export default function JumpBack({ active, untranslated, onActivate, onReturn }: {
  active: number;
  untranslated: number | null;
  onActivate: (i: number) => void;
  onReturn: () => void;
}) {
  const nextWhere = useWhere(untranslated);
  const activeWhere = useWhere(active);
  const showNext = untranslated != null && nextWhere !== null && nextWhere !== "visible";
  const sameLine = untranslated === active;
  const showBack = activeWhere !== null && activeWhere !== "visible" && !(showNext && sameLine);
  if (!showNext && !showBack) return null;
  return (
    <div className="jump-back">
      {showNext && (
        <button type="button" className="primary" onClick={() => onActivate(untranslated)}>
          {nextWhere === "above" ? <ArrowUp /> : <ArrowDown />}
          Next untranslated · line {untranslated + 1}
        </button>
      )}
      {showBack && (
        <button type="button" onClick={onReturn}>
          {activeWhere === "above" ? <ArrowUp /> : <ArrowDown />}
          Back to editing · line {active + 1}
        </button>
      )}
    </div>
  );
}
