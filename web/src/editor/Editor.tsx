import { undo } from "@codemirror/commands";
import type { EditorView } from "@codemirror/view";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import SpellMenu from "./SpellMenu";
import { useSpell } from "./useSpell";
import { api, call, type Schemas } from "../api/client";
import type { Misspelling } from "./LineCard";
import CardList from "./CardList";
import CodeEditor, { replaceDoc, setMarks } from "./CodeEditor";
import FindBar from "./FindBar";
import ImageCard from "./ImageCard";
import { buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, parseLineNumber, progress } from "./rows";
import PhraseDialog from "./PhraseDialog";
import { readingMode, type ReadingMode } from "./ruby";
import { useReadings } from "./useReadings";
import StatusBar, { linesText, type Crumbs } from "./StatusBar";
import StickyTop from "./StickyTop";
import KeyHelp from "./KeyHelp";
import MtPanels from "./MtPanels";
import TmPanel from "./TmPanel";
import ChapterNav from "./ChapterBar";
import { chapterNeighbours } from "./chapterNav";
import JumpBack from "./JumpBack";
import ChapterEnd from "./ChapterEnd";
import { useLeave } from "./useLeave";
import { useNotice } from "./useNotice";
import { copyText, unsavedText } from "./clipboard";
import { useAllVolumes, useDocuments, useSeriesList } from "../library/queries";
import { shownTitle } from "../library/shelf";
import { useEditor } from "./useEditor";
import { useFind } from "./useFind";
import { useBindings, useEditorKeys } from "./useEditorKeys";
import { assignSlots } from "./useSlots";
import { useDebounced } from "./useDebounced";
import { AidCount } from "./AidCount";
import { readAidsOpen, writeAidsOpen } from "./aidsPref";
import { AidsColumn, ChapterMenu, EmptyChapter, StatusTools } from "./EditorTools";
import { runAction } from "./runAction";

type Data = Schemas["DocumentLines"];

export default function Editor({ id, data }: { id: number; data: Data }) {
  const lines = data.lines;
  const startAt = useMemo(() => {
    const p = data.document.last_position;
    return lines[p] && hasContent(lines[p].raw_text) ? p : (firstContent(lines) ?? 0);
    // the opening position only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const ed = useEditor(id, lines, startAt);
  const view = useRef<EditorView | null>(null);
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const fontPx = Number(settings.data?.editor_font_px ?? 18);
  const images = useQuery({
    queryKey: ["document", id, "images"],
    queryFn: () => call(api.GET("/documents/{document_id}/images", { params: { path: { document_id: id } } })),
  });
  const rows = useMemo(() => buildRows(lines, images.data ?? []), [lines, images.data]);
  const tmVisible = settings.data?.tm_visible !== false;
  const mtVisible = settings.data?.mt_visible !== false;
  const imagesCollapsed = Boolean(settings.data?.images_collapsed);
  const glossaryRuby = settings.data?.glossary_ruby === true;
  const stats = useMemo(() => progress(lines, ed.texts), [lines, ed.texts]);
  const backends = useQuery({ queryKey: ["mt", "backends"], queryFn: () => call(api.GET("/mt/backends")) });
  // Alt+1..9 pick a fixed suggestion: the desktop's two memory matches, then each backend.
  const slots = useMemo(() => assignSlots(backends.data?.enabled ?? []), [backends.data]);
  const onReady = useCallback((v: EditorView | null) => { view.current = v; }, []);
  // Everything behind a modal <dialog> is inert until it has gone.
  const focusAfterDialog = useCallback(() => void setTimeout(() => view.current?.focus()), []);
  const current = lines[ed.active];
  const queryClient = useQueryClient();
  const saveSetting = (key: string, value: unknown) => {
    queryClient.setQueryData(["settings"], { ...settings.data, [key]: value });
    void call(api.PUT("/settings", { body: { [key]: value } })).catch(() => {});
  };
  const setFont = (px: number) => saveSetting("editor_font_px", Math.max(12, Math.min(32, px)));
  const edRef = useRef(ed);
  edRef.current = ed;
  // The text selected when the Chapter actions menu opens, captured on the button press
  // (a click moves focus and drops the DOM selection before the item runs).
  const pendingSelection = useRef("");
  const find = useFind(rows, ed.texts, ed.active, ed.activate, glossaryRuby);
  const { hit } = find;
  const activate = useCallback((i: number | null) => { find.stepped.current = false; edRef.current.activate(i); }, [find.stepped]);
  const seriesId = data.document.series_id;
  const spell = useSpell(seriesId, lines.map((l) => ed.texts[l.line_number] ?? ""));
  const [menu, setMenu] = useState<{ x: number; y: number; word: Misspelling } | null>(null);
  const [phrase, setPhrase] = useState<string | null>(null);
  const [goTo, setGoTo] = useState<string | null>(null);
  const [goToError, setGoToError] = useState<string | null>(null);
  const [wantEnd, setWantEnd] = useState(false);
  const { notice, setNotice } = useNotice(ed.active);
  const docs = useDocuments();
  const volumes = useAllVolumes();
  const seriesList = useSeriesList();
  const volumeId = data.document.volume_id;
  const crumbs: Crumbs = {
    series: { id: seriesId, title: seriesList.data?.find((s) => s.id === seriesId)?.title ?? "Series" },
    volume: { id: volumeId, label: volumes.data?.find((v) => v.id === volumeId)?.label ?? "Volume" },
  };
  const { leave, waiting, asking, goAnyway, stay } = useLeave(ed.store, ed.save.state, focusAfterDialog);
  const [showKeys, setShowKeys] = useState(false);
  const [aidsOpen, setAidsOpen] = useState(readAidsOpen);
  const toggleAids = () => setAidsOpen((open) => {
    writeAidsOpen(!open);
    return !open;
  });
  // Held-key stepping passes many lines; the hidden announcement follows once it stops.
  const announcedLine = useDebounced((current?.line_number ?? ed.active) + 1, 400);
  const chapters = useMemo(() => chapterNeighbours(docs.data ?? [], id), [docs.data, id]);
  const listed = docs.data?.find((d) => d.id === id);
  // The server answered, but it has no such line: the source was edited elsewhere, and the
  // text only exists in this tab now.
  const missingText = ed.missing.length
    ? `${linesText(ed.missing.map((n) => n + 1))} ${ed.missing.length === 1 ? "no longer exists" : "no longer exist"}; reload the chapter`
    : null;
  const barSave = missingText ? { state: "error" as const, error: missingText } : ed.save;
  const addWord = async (word: string, scope: "series" | "all") => {
    word = word.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
    if (!word || /\s/.test(word)) return setNotice("Select a single word first");
    if (word.includes("/")) return setNotice("Words with / can't be added");
    try {
      if (scope === "series") await call(api.PUT("/series/{series_id}/words/{word}", { params: { path: { series_id: seriesId, word } } }));
      else await call(api.PUT("/words/{word}", { params: { path: { word } } }));
      spell.forget();
      setNotice(scope === "series" ? `Added \u201c${word}\u201d to the series dictionary` : `Added \u201c${word}\u201d to your dictionary`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not add the word");
    }
  };
  const onContextMenu = (v: EditorView, e: MouseEvent) => {
    const pos = v.posAtCoords({ x: e.clientX, y: e.clientY });
    const text = v.state.doc.toString();
    const word = pos == null ? undefined
      : spell.misspelled(text).find((m) => m.start <= pos && pos <= m.end && text.slice(m.start, m.end) === m.word);
    if (!word) return false;
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, word });
    return true;
  };
  const closeMenu = useCallback(() => { setMenu(null); view.current?.focus(); }, []);
  const mode = readingMode(settings.data?.reading_aid);
  const shown = current ? (glossaryRuby ? current.plain_text : ed.parse === -2 ? current.raw_text : current.display_text) : "";
  const readings = useReadings(shown, mode);
  const setMode = (m: ReadingMode) => saveSetting("reading_aid", m);
  const activeText = current ? (ed.texts[current.line_number] ?? "") : "";
  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const marks = spell.known(activeText)
      ? spell.misspelled(activeText).map((m) => ({ from: m.start, to: m.end, cls: "misspelled" }))
      : [];
    if (hit && hit.index === ed.active && hit.field === "translation") marks.push({ from: hit.from, to: hit.to, cls: "find-current" });
    v.dispatch({ effects: setMarks.of(marks) });
  }, [spell.misspelled, spell.known, activeText, hit, ed.active]);
  const run = (action: string) => runAction(action, {
    ed, lines, phrase, view, pendingSelection, chapters, mode, readingsAvailable: readings.available,
    tmVisible, mtVisible, glossaryRuby, fontPx, setWantEnd, setNotice, setGoTo, setGoToError, setFont,
    setMode, setShowKeys, setMenu, saveSetting, addWord: (word, scope) => void addWord(word, scope),
    activate, showFind: find.show, misspelled: spell.misspelled, leave, setPhrase,
  });
  const bindings = useBindings();
  const closeFind = () => {
    if (!find.open) return false;
    find.close();
    view.current?.focus();
    return true;
  };
  useEditorKeys(bindings, run, () => view.current?.focus(), closeFind);
  // Every hook stays above this early return; later tasks add theirs here too and read
  // `current?.` (it is undefined for a chapter with no lines).

  const firstLeft = firstUntranslated(lines, ed.texts);
  // A move to the active line itself only brings its card back into view (activate would change nothing).
  const returnToActive = () => {
    document.querySelector(`article[data-index="${ed.active}"]`)?.scrollIntoView({ block: "center" });
    view.current?.focus();
  };
  // Land on the end card's button once it exists (the chapter list may still be loading).
  useEffect(() => {
    if (!wantEnd) return;
    const primary = document.querySelector<HTMLElement>(".chapter-end .primary");
    if (primary) {
      primary.scrollIntoView({ block: "center" });
      primary.focus();
      setWantEnd(false);
    } else if (docs.data !== undefined) {
      setWantEnd(false); // there is no way on from here
    }
  });
  const goToLine = (i: number) => (i === ed.active ? returnToActive() : activate(i));
  const chapterMenu = (withLines: boolean) => (
    <ChapterMenu id={id} seriesId={seriesId} withLines={withLines} bindings={bindings}
      glossaryRuby={glossaryRuby} imagesCount={images.data?.length ?? 0} imagesCollapsed={imagesCollapsed}
      readingsOff={!readings.available} spellOff={!spell.available}
      onLeave={(to) => void leave(to)} onGoToLine={() => run("go_to_line")} onAddPhrase={() => run("add_phrase")}
      onShowKeys={() => setShowKeys(true)}
      onGlossaryRuby={() => { saveSetting("glossary_ruby", !glossaryRuby); view.current?.focus(); }}
      onImages={() => { saveSetting("images_collapsed", !imagesCollapsed); view.current?.focus(); }}
      onPointerDown={() => { pendingSelection.current = window.getSelection()?.toString().trim() ?? ""; }}
      onClearSelection={() => { pendingSelection.current = ""; }} />
  );
  // The lines whose text the server has not taken: the dirty ones while a save is failing,
  // plus any the server says are gone. Those keep their text here, and Copy offers it.
  const failed = ed.save.error ? ed.store.unsaved().map((e) => e.line_number) : [];
  const unsaved = [...new Set([...failed, ...ed.missing])].sort((a, b) => a - b);
  const unsavedLines = unsaved.map((n) => n + 1);
  const unsavedSet = useMemo(() => new Set(unsaved), [unsaved.join(",")]);
  const copyUnsaved = () => {
    const edits = ed.store.unsaved();
    const all = [...edits, ...ed.missing
      .filter((n) => !edits.some((e) => e.line_number === n))
      .map((n) => ({ line_number: n, translated_text: ed.texts[n] ?? "" }))];
    void copyText(unsavedText(all)).then((ok) => { if (!ok) setNotice("Could not copy the text"); });
  };
  const restoredNotice = ed.restored
    ? `Restored ${ed.restored} unsaved ${ed.restored === 1 ? "line" : "lines"} from earlier in this tab`
    : null;
  const leaveDialog = asking && (
    <ConfirmDialog title="Leave with unsaved lines?" danger confirmLabel="Leave anyway"
      message={<p>{linesText(asking.lines)} could not be saved: {asking.error} The text is kept in this tab and sent again when you reopen this chapter here. Closing the tab loses it.</p>}
      onConfirm={goAnyway} onClose={stay} />
  );
  const statusBar = (phraseText: string | null, tools: ReactNode) => (
    <StatusBar translated={stats.done} lineCount={stats.total} percent={stats.percent}
      phrase={phraseText} save={barSave} unsavedLines={barSave === ed.save ? unsavedLines : []}
      permanent={ed.savePermanent || Boolean(missingText)}
      onRetry={() => void ed.store.flush()} onCopy={copyUnsaved}
      notice={restoredNotice ?? notice} waiting={waiting ? "Leaving once saved. Esc to stay." : null}
      nav={listed && <ChapterNav doc={listed} chapters={chapters} crumbs={crumbs} onLeave={(to) => void leave(to)}
        prevKey={bindings.prev_chapter} nextKey={bindings.next_chapter}
        onGo={(d) => void leave(`/documents/${d.id}`)} />}
      tools={tools} />
  );
  const chapterEnd = (
    <ChapterEnd doc={listed} next={chapters.next} seriesId={seriesId} total={stats.total} done={stats.done}
      words={stats.words} firstLeft={firstLeft} onJump={goToLine} onLeave={(to) => void leave(to)} />
  );

  if (!rows.some((r) => r.kind === "line")) {
    // an illustration-only or empty chapter still shows its images and the way on
    return (
      <EmptyChapter id={id} fontPx={fontPx} images={images} imagesCollapsed={imagesCollapsed}
        lineCount={lines.length} chapters={chapters.volume}
        top={<StickyTop>{statusBar(null, <>{chapterMenu(false)}</>)}</StickyTop>}
        leaveDialog={leaveDialog} chapterEnd={chapterEnd} />
    );
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} historyKey={`${id}:${n}`} value={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} autoFocus={!find.stepped.current} onContextMenu={onContextMenu} />
  );
  const useText = (t: string) => {
    const replacing = Boolean(ed.texts[n]) && ed.texts[n] !== t;
    // Through the view, so the replaced translation is one Ctrl+Z away.
    if (view.current) replaceDoc(view.current, t);
    else ed.setText(n, t);
    if (replacing) {
      setNotice(
        <span className="sb-undo">Replaced line {n + 1}.
          <button type="button" className="small" onClick={() => {
            if (!view.current) return;
            undo(view.current);
            view.current.focus();
          }}>Undo</button>
        </span>,
      );
    }
  };
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <h1 className="visually-hidden">{shownTitle(data.document)}</h1>
      <div role="status" className="visually-hidden">Line {announcedLine} of {lines.length}</div>
      <StickyTop>
      {statusBar(ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null, (
        <StatusTools mode={mode} onMode={setMode} readings={readings} tmVisible={tmVisible} mtVisible={mtVisible}
          bindings={bindings} onToggleTm={() => saveSetting("tm_visible", !tmVisible)}
          onToggleMt={() => saveSetting("mt_visible", !mtVisible)} onShowKeys={() => setShowKeys(true)}
          menu={chapterMenu(true)} />
      ))}
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={find.at} total={find.total}
          onNeedle={find.setNeedle} onStep={find.step}
          onClose={() => { find.close(); view.current?.focus(); }} />
      )}
      </StickyTop>
      <main className="editor-layout">
      <div className="editor">
        <CardList rows={rows} active={ed.active} parse={ed.parse} texts={ed.texts}
          onActivate={activate} editor={editor} highlight={hit} hits={find.hits} unsaved={unsavedSet}
          misspelled={spell.misspelled} readings={readings.ruby} glossaryRuby={glossaryRuby}
          renderImage={(image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} chapters={chapters.volume} lineCount={lines.length} />} />
        {chapterEnd}
        <JumpBack active={ed.active} untranslated={firstLeft} onActivate={goToLine} onReturn={returnToActive} />
      </div>
      {(tmVisible || mtVisible) && (
        <AidCount>
          <AidsColumn open={aidsOpen} onToggle={toggleAids}>
            {tmVisible && <TmPanel documentId={id} lineNumber={n} onUse={useText} slots={slots} bindings={bindings} />}
            {mtVisible && <MtPanels documentId={id} lineNumber={n} translated={Boolean(ed.texts[n])} onUse={useText}
              slots={slots} bindings={bindings} />}
          </AidsColumn>
        </AidCount>
      )}
      </main>
      {phrase !== null && <PhraseDialog initial={phrase} onClose={() => { setPhrase(null); focusAfterDialog(); }} onSave={async (p, t) => {
        await call(api.POST("/series/{series_id}/glossary", { params: { path: { series_id: seriesId } }, body: { phrase: p, translation: t } }));
        await queryClient.invalidateQueries({ queryKey: ["glossary", seriesId] });
        await queryClient.invalidateQueries({ queryKey: ["document"] });
        setNotice(`Added \u201c${p}\u201d to the glossary`);
      }} />}
      {leaveDialog}
      {goTo !== null && (
        <PromptDialog title="Go to line" label={`Line number (1\u2013${lines.length})`} initial={goTo}
          confirmLabel="Go" error={goToError}
          onSubmit={(value) => {
            const n = parseLineNumber(value, lines.length);
            if (n === null) {
              setGoToError(`Enter a line number from 1 to ${lines.length}`);
              return;
            }
            setGoTo(null);
            setGoToError(null);
            focusAfterDialog();
            const at = lineAtOrAfter(lines, n);
            if (at !== null) activate(at);
          }}
          onClose={() => { setGoTo(null); setGoToError(null); focusAfterDialog(); }} />
      )}
      {showKeys && <KeyHelp bindings={bindings} onClose={() => { setShowKeys(false); focusAfterDialog(); }}
        onChange={() => { setShowKeys(false); void leave("/settings/shortcuts"); }} />}
      {menu && <SpellMenu {...menu} onClose={closeMenu} onAdd={(scope) => { void addWord(menu.word.word, scope); closeMenu(); }}
        onPick={(s) => {
          const v = view.current;
          const { start, end, word } = menu.word;
          if (v && end <= v.state.doc.length && v.state.sliceDoc(start, end) === word) v.dispatch({ changes: { from: start, to: end, insert: s } });
          closeMenu();
        }} />}
    </div>
  );
}
