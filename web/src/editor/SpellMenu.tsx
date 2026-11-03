import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { moveMenuFocus } from "../ui/Menu";
import type { Misspelling } from "./LineCard";

interface Props {
  x: number;
  y: number;
  word: Misspelling;
  onPick(suggestion: string): void;
  onAdd(scope: "series" | "all"): void;
  onClose(): void;
}

/** The right-click menu on a misspelled word: suggestions, then "Add to dictionary" for this
 * series or for all series (the account dictionary). */
export default function SpellMenu({ x, y, word, onPick, onAdd, onClose }: Props) {
  const menu = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  useLayoutEffect(() => {
    const r = menu.current?.getBoundingClientRect();
    if (r) setPos({ left: Math.max(0, Math.min(x, window.innerWidth - r.width)), top: Math.max(0, Math.min(y, window.innerHeight - r.height)) });
  }, [x, y]);
  useEffect(() => {
    menu.current?.querySelector("button")?.focus();
    const away = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) onClose(); };
    window.addEventListener("mousedown", away);
    return () => window.removeEventListener("mousedown", away);
  }, [onClose]);
  return (
    <div ref={menu} className="spell-menu" role="menu" style={pos}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        else moveMenuFocus(e, menu.current);
      }}>
      {word.suggestions.length ? (
        word.suggestions.map((s) => (
          <button key={s} role="menuitem" onClick={() => onPick(s)}><strong>{s}</strong></button>
        ))
      ) : (
        <span className="muted">No suggestions</span>
      )}
      <hr />
      <button role="menuitem" onClick={() => onAdd("series")}>Add “{word.word}” to this series</button>
      <button role="menuitem" onClick={() => onAdd("all")}>Add “{word.word}” for all series</button>
    </div>
  );
}
