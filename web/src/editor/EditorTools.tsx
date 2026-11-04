import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router";
import type { Doc } from "../library/shelf";
import Menu from "../ui/Menu";
import { Help, Memory, Translate } from "../ui/icons";
import { useAidCount } from "./AidCount";
import ImageCard from "./ImageCard";
import ReadingSwitch from "./ReadingSwitch";
import type { Image } from "./rows";
import type { ReadingMode } from "./ruby";

/** The chapter's ⋯ menu: the ways out of the chapter, the editor extras and the aids that need
 *  no permanent space. A reason an aid is missing shows here as plain text, not in a tooltip. */
export function ChapterMenu({
  id, seriesId, withLines, bindings, glossaryRuby, imagesCount, imagesCollapsed, readingsOff, spellOff,
  onLeave, onGoToLine, onAddPhrase, onShowKeys, onGlossaryRuby, onImages, onPointerDown, onClearSelection,
}: {
  id: number;
  seriesId: number;
  withLines: boolean;
  bindings: Record<string, string>;
  glossaryRuby: boolean;
  imagesCount: number;
  imagesCollapsed: boolean;
  readingsOff: boolean;
  spellOff: boolean;
  onLeave(to: string): void;
  onGoToLine(): void;
  onAddPhrase(): void;
  onShowKeys(): void;
  onGlossaryRuby(): void;
  onImages(): void;
  /** Captures the selection made before the button moved focus. */
  onPointerDown(): void;
  onClearSelection(): void;
}) {
  const keyed = (label: string, action: string) => `${label} (${bindings[action]})`;
  return (
    <Menu label={<span title={`Chapter actions · ? for keyboard shortcuts (${bindings.key_help})`}>⋯</span>}
      buttonLabel="Chapter actions" onPointerDown={onPointerDown}>
      {(close) => {
        const actions = ([
          ["Edit source", () => onLeave(`/documents/${id}/source`)],
          ["Split chapter", () => onLeave(`/documents/${id}/split`)],
          ...(withLines ? [[keyed("Go to line…", "go_to_line"), onGoToLine] as const] : []),
          ["Series glossary", () => onLeave(`/series/${seriesId}?tab=glossary`)],
          ...(withLines ? [[keyed("Add glossary phrase…", "add_phrase"), onAddPhrase] as const] : []),
          ["Series tools", () => onLeave(`/series/${seriesId}?tab=tools`)],
          ...(withLines ? [[keyed("Keyboard shortcuts (?)", "key_help"), onShowKeys] as const] : []),
        ] as const);
        // The aids that need no permanent space live here, as checkboxes.
        const toggles = [
          ...(withLines ? [(
            <button key="glossary-ruby" type="button" role="menuitemcheckbox" aria-checked={glossaryRuby}
              title="Shows glossary matches above the source"
              onClick={() => {
                close();
                onGlossaryRuby();
              }}>{keyed("Glossary ruby", "toggle_glossary_ruby")}</button>
          )] : []),
          ...(imagesCount ? [(
            <button key="images" type="button" role="menuitemcheckbox" aria-checked={!imagesCollapsed}
              title="Show chapter images"
              onClick={() => {
                close();
                onImages();
              }}>Images</button>
          )] : []),
        ];
        return (
          <>
            {withLines && readingsOff && (
              // A link while readings are off: the setting that turns them on is one click away.
              <Link role="menuitem" className="menu-hint" to="/settings/mt" onClick={(e) => {
                if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                close();
                onLeave("/settings/mt");
              }}>Readings unavailable: needs MeCab · Set up</Link>
            )}
            {withLines && spellOff && (
              <button type="button" role="menuitem" className="menu-hint" aria-disabled="true" disabled>
                Spellcheck unavailable: no dictionary on the server
              </button>
            )}
            {withLines && (readingsOff || spellOff) && <div className="menu-sep" role="presentation" />}
            {actions.map(([text, act]) => (
              <button key={text} type="button" role="menuitem"
                onClick={() => { close(); act(); onClearSelection(); }}>{text}</button>
            ))}
            {toggles.length > 0 && <div className="menu-sep" role="presentation" />}
            {toggles}
          </>
        );
      }}
    </Menu>
  );
}

/** The status bar's right zone: the reading modes, the two aid toggles, the key sheet and the
 *  chapter menu. A mouse press on a toggle keeps the caret where it is, so typing carries on
 *  (the status bar holds that rule). */
export function StatusTools({
  mode, onMode, readings, tmVisible, mtVisible, bindings, onToggleTm, onToggleMt, onShowKeys, menu,
}: {
  mode: ReadingMode;
  onMode(mode: ReadingMode): void;
  readings: { available: boolean; message: string };
  tmVisible: boolean;
  mtVisible: boolean;
  bindings: Record<string, string>;
  onToggleTm(): void;
  onToggleMt(): void;
  onShowKeys(): void;
  menu: ReactNode;
}) {
  const keyed = (label: string, action: string) => `${label} (${bindings[action]})`;
  return (
    <>
      <ReadingSwitch mode={mode} onChange={onMode} disabled={!readings.available} title={readings.message} />
      <span className="sb-divider" aria-hidden="true" />
      <div role="group" aria-label="Aids" className="sb-aids">
        <button type="button" className="icon" aria-label="Translation memory" title={keyed("Translation memory", "toggle_tm")}
          aria-pressed={tmVisible} onClick={onToggleTm}>
          <Memory /><span className="sb-label" aria-hidden="true">Memory</span>
        </button>
        <button type="button" className="icon" aria-label="Machine translation" title={keyed("Machine translation", "toggle_mt")}
          aria-pressed={mtVisible} onClick={onToggleMt}>
          <Translate /><span className="sb-label" aria-hidden="true">MT</span>
        </button>
      </div>
      <span className="sb-divider" aria-hidden="true" />
      <button type="button" className="icon sb-keys" aria-label="Keyboard shortcuts"
        title={keyed("Keyboard shortcuts", "key_help")} onClick={onShowKeys}>
        <Help /><span className="sb-label" aria-hidden="true">Keys</span>
      </button>
      <span className="sb-divider" aria-hidden="true" />
      {menu}
    </>
  );
}

/** The suggestion column: one header row that folds it to a peek bar at every width, then the
 *  cards in their fixed DOM order (the Alt+N slots follow that order). The peek bar says how
 *  many cards are ready, and the choice is remembered in this browser. */
export function AidsColumn({ open, onToggle, children }: {
  open: boolean;
  onToggle(): void;
  children: ReactNode;
}) {
  const ready = useAidCount();
  return (
    <div className={`side-col${open ? "" : " collapsed"}`}>
      <h2 className="visually-hidden">Suggestions</h2>
      <button type="button" className="side-col-toggle" aria-expanded={open} onClick={onToggle}>
        <span>Suggestions</span>
        <span className="aids-meta">
          {!open && ready > 0 && <span className="aids-ready">{ready} ready</span>}
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        </span>
      </button>
      {children}
    </div>
  );
}

/** A chapter with no lines still shows its images and the way on; nothing else fits it. */
export function EmptyChapter({ id, fontPx, images, imagesCollapsed, lineCount, chapters, top, leaveDialog, chapterEnd }: {
  id: number;
  fontPx: number;
  images: { isPending: boolean; data?: Image[] };
  imagesCollapsed: boolean;
  lineCount: number;
  chapters: Doc[];
  top: ReactNode; // the sticky status bar
  leaveDialog: ReactNode;
  chapterEnd: ReactNode;
}) {
  if (images.isPending) {
    return (
      <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
        <main className="editor">
          <div className="editor-skel" aria-hidden="true"><span /><span /><span /><span /></div>
        </main>
      </div>
    );
  }
  const only = images.data?.length ? "has only images, no source text" : "has no source text yet";
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      {top}
      {leaveDialog}
      <main className="editor">
        <p>This chapter {only}. <Link to={`/documents/${id}/source`}>Edit source</Link></p>
        {(images.data ?? []).map((image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} chapters={chapters} lineCount={lineCount} />)}
        {chapterEnd}
      </main>
    </div>
  );
}
