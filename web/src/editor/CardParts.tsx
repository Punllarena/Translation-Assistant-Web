import type { ReactNode } from "react";

export type CardKind = "busy" | "empty" | "error" | "info";

/** One way of saying what an aid card is doing. A busy card shows dots instead of a bare
 *  ellipsis; an error speaks once, as an alert; empty and info stay quiet. */
export function CardStatus({ kind, children }: { kind: CardKind; children?: ReactNode }) {
  if (kind === "busy") {
    return (
      <span className="card-status card-busy" role="status">
        <span className="card-spinner" aria-hidden="true"><span /><span /><span /></span>
        <span className="visually-hidden">{children ?? "Working"}</span>
      </span>
    );
  }
  if (kind === "error") return <p className="card-status card-error" role="alert">{children}</p>;
  if (kind === "empty") return <p className="card-status card-empty muted">{children}</p>;
  return <p className="card-status card-info muted">{children}</p>;
}

/** A ready card says so in words, not by its coloured edge alone. */
export function CardReady() {
  return <span className="card-ready">Ready</span>;
}

/** The small button every card uses for its actions; `use` is the shared Use look, with the
 *  key that picks it printed beside the word. */
export function CardAction({ children, onClick, slot, keyLabel, label, title, tone = "plain", disabled }: {
  children: ReactNode;
  onClick?(): void;
  slot?: number;
  keyLabel?: string;
  label?: string;
  title?: string;
  tone?: "plain" | "use";
  disabled?: boolean;
}) {
  return (
    <button type="button" className={`small card-action${tone === "use" ? " card-use" : ""}`}
      data-use={slot} aria-label={label} title={title} disabled={disabled} onClick={onClick}>
      {keyLabel && <span className="use-key" aria-hidden="true">{keyLabel}</span>}
      {children}
    </button>
  );
}
