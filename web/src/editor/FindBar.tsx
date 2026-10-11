import { useEffect, useRef } from "react";

interface Props {
  needle: string;
  onNeedle(needle: string): void;
  position: number; // -1 before the first step
  total: number;
  onStep(dir: 1 | -1): void;
  onClose(): void;
}

/** Find (spec §5): Enter next, Shift+Enter previous, Escape closes; wraps; n/total. */
export default function FindBar({ needle, onNeedle, position, total, onStep, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <div className="findbar" role="search">
      <input ref={input} aria-label="Find" value={needle} className={needle && !total ? "notfound" : undefined}
        onChange={(e) => onNeedle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onStep(e.shiftKey ? -1 : 1);
          } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          }
        }} />
      <span aria-live="polite">{needle ? `${total ? position + 1 : 0}/${total}` : ""}</span>
      <button onClick={() => onStep(-1)} aria-label="Previous match">↑</button>
      <button onClick={() => onStep(1)} aria-label="Next match">↓</button>
      <button onClick={onClose} aria-label="Close find">×</button>
    </div>
  );
}
