import type { ReactNode } from "react";
import { NO_HITS, type Hit } from "./find";
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
  hits?: Hit[]; // every match, for the cards to mark
  misspelled?(text: string): Misspelling[];
  renderImage?(image: Image): ReactNode;
  readings?: Ruby[]; // the active card's ruby when the reading aid is on
  glossaryRuby?: boolean; // show the original text with glossary translations as ruby
  unsaved?: ReadonlySet<number>; // line numbers whose text is not on the server
}

export default function CardList({ rows, active, parse, texts, onActivate, editor, highlight, hits = NO_HITS, misspelled, renderImage, readings, glossaryRuby = false, unsaved }: Props) {
  return (
    <>
      {rows.map((row) => {
        if (row.kind === "image") return renderImage?.(row.image) ?? null;
        const text = texts[row.line.line_number] ?? "";
        const isActive = row.index === active;
        return (
          <LineCard key={row.line.line_number} index={row.index} line={row.line} active={isActive}
            parse={isActive ? parse : -1} text={text} unsaved={unsaved?.has(row.line.line_number) ?? false}
            highlight={highlight?.index === row.index ? highlight : null} hits={hits}
            misspelled={misspelled?.(text) ?? NONE} onActivate={onActivate}
            editor={isActive ? editor : undefined} readings={isActive ? readings : undefined}
            glossaryRuby={glossaryRuby} />
        );
      })}
    </>
  );
}
