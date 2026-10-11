import { useEffect, useRef } from "react";
import type { Misspelling } from "./LineCard";

interface Props {
  x: number;
  y: number;
  word: Misspelling;
  onPick(suggestion: string): void;
  onAdd(): void;
  onClose(): void;
}

/** The right-click menu on a misspelled word: suggestions, then "Add to dictionary". */
export default function SpellMenu({ x, y, word, onPick, onAdd, onClose }: Props) {
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    menu.current?.querySelector("button")?.focus();
    const away = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) onClose(); };
    window.addEventListener("mousedown", away);
    return () => window.removeEventListener("mousedown", away);
  }, [onClose]);
  return (
    <div ref={menu} className="spell-menu" role="menu" style={{ left: x, top: y }}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      {word.suggestions.length ? (
        word.suggestions.map((s) => (
          <button key={s} role="menuitem" onClick={() => onPick(s)}><strong>{s}</strong></button>
        ))
      ) : (
        <span className="muted">No suggestions</span>
      )}
      <hr />
      <button role="menuitem" onClick={onAdd}>Add “{word.word}” to the dictionary</button>
    </div>
  );
}
