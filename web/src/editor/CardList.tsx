import type { ReactNode } from "react";
import type { Hit } from "./find";
import LineCard, { NONE, type Misspelling } from "./LineCard";
import type { Image, Row } from "./rows";
import type { Ruby } from "./ruby";

interface Props {
  rows: Row[];
  active: number;
  parse: number;
  texts: Record<number, string>;
  onActivate(index: number): void;
  editor: ReactNode;
  highlight?: Hit | null;
  misspelled?(text: string): Misspelling[];
  renderImage?(image: Image): ReactNode;
  readings?: Ruby[]; // the active card's ruby when the reading aid is on
}

export default function CardList({ rows, active, parse, texts, onActivate, editor, highlight, misspelled, renderImage, readings }: Props) {
  return (
    <>
      {rows.map((row) => {
        if (row.kind === "image") return renderImage?.(row.image) ?? null;
        const text = texts[row.line.line_number] ?? "";
        const isActive = row.index === active;
        return (
          <LineCard key={row.line.line_number} index={row.index} line={row.line} active={isActive}
            parse={isActive ? parse : -1} text={text}
            highlight={highlight?.index === row.index ? highlight : null}
            misspelled={misspelled?.(text) ?? NONE} onActivate={onActivate}
            editor={isActive ? editor : undefined} readings={isActive ? readings : undefined} />
        );
      })}
    </>
  );
}
