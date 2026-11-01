import type { EditorView } from "@codemirror/view";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import SpellMenu from "./SpellMenu";
import { useSpell } from "./useSpell";
import { api, call, type Schemas } from "../api/client";
import type { Misspelling } from "./LineCard";
import CardList from "./CardList";
import CodeEditor, { insertAtCursor, replaceDoc, setMarks } from "./CodeEditor";
import FindBar from "./FindBar";
import ImageCard from "./ImageCard";
import { PUNCTUATIONS } from "./keymap";
import { advanceParse, retreatParse } from "./parse";
import { buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, nextContent, parseLineNumber, prevContent, progress } from "./rows";
import PhraseDialog from "./PhraseDialog";
import ReadingSwitch from "./ReadingSwitch";
import { readingMode, type ReadingMode } from "./ruby";
import { useReadings } from "./useReadings";
import StatusBar, { linesText, type Crumbs } from "./StatusBar";
import StickyTop from "./StickyTop";
import KeyHelp from "./KeyHelp";
import Menu from "../ui/Menu";
import { Memory, Picture, Ruby, Translate } from "../ui/icons";
import MtPanels from "./MtPanels";
import TmPanel from "./TmPanel";
import ChapterNav from "./ChapterBar";
import { chapterNeighbours } from "./chapterNav";
import JumpBack from "./JumpBack";
import ChapterEnd from "./ChapterEnd";
import { useLeave } from "./useLeave";
import { useNotice } from "./useNotice";
import { copyText } from "./clipboard";
import { useAllVolumes, useDocuments, useSeriesList } from "../library/queries";
import { shownTitle } from "../library/shelf";
import { useEditor } from "./useEditor";
import { useFind } from "./useFind";
import { useBindings, useEditorKeys } from "./useEditorKeys";
import { assignSlots } from "./useSlots";

type Data = Schemas["DocumentLines"];

const READING_ORDER: ReadingMode[] = ["off", "hiragana", "katakana", "romaji"];

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
  const run = (action: string) => {
    const at = ed.active;
    if (!lines[at] || phrase !== null) return;
    switch (action) {
      case "save_next": {
        void ed.store.flush();
        const next = nextContent(lines, at);
        if (next !== null) {
          activate(next);
          break;
        }
        // The last line: the way on is the end card, whose button may still be loading.
        setWantEnd(true);
        break;
      }
      case "next":
      case "next_alt":
        activate(nextContent(lines, at));
        break;
      case "prev":
      case "prev_alt":
        activate(prevContent(lines, at));
        break;
      case "first":
        activate(firstContent(lines));
        break;
      case "next_untranslated": {
        // desktop: only from a line that already has a translation
        if (!ed.texts[lines[at].line_number]) {
          setNotice("This line has no translation yet");
          break;
        }
        const next = firstUntranslated(lines, ed.texts);
        if (next === null) setNotice("No untranslated lines left");
        else activate(next);
        break;
      }
      case "parse_next":
        ed.setParse((p) => advanceParse(p, lines[at].sentences.length));
        break;
      case "parse_prev":
        ed.setParse((p) => retreatParse(p, lines[at].replaced));
        break;
      case "go_to_line":
        setGoToError(null);
        setGoTo("");
        break;
      case "font_larger":
        setFont(fontPx + 1);
        break;
      case "font_smaller":
        setFont(fontPx - 1);
        break;
      case "add_word": {
        const v = view.current;
        if (v) {
          const { from, to } = v.state.selection.main;
          void addWord(v.state.sliceDoc(from, to).trim(), "series");
        }
        break;
      }
      case "add_phrase":
        setPhrase(pendingSelection.current || window.getSelection()?.toString().trim() || "");
        break;
      case "find":
        find.show();
        break;
      case "next_chapter":
        if (chapters.next) void leave(`/documents/${chapters.next.id}`);
        break;
      case "prev_chapter":
        if (chapters.prev) void leave(`/documents/${chapters.prev.id}`);
        break;
      case "toggle_tm":
        saveSetting("tm_visible", !tmVisible);
        break;
      case "toggle_mt":
        saveSetting("mt_visible", !mtVisible);
        break;
      case "toggle_glossary_ruby":
        saveSetting("glossary_ruby", !glossaryRuby);
        break;
      case "cycle_reading":
        if (readings.available) setMode(READING_ORDER[(READING_ORDER.indexOf(mode) + 1) % READING_ORDER.length]);
        break;
      case "key_help":
        setShowKeys(true);
        break;
      case "retry_save":
        void ed.store.flush();
        break;
      case "spell_open": {
        const v = view.current;
        if (!v) break;
        const words = spell.misspelled(v.state.doc.toString());
        if (!words.length) {
          setNotice("No misspelled words on this line");
          break;
        }
        // The word under or after the caret, else the first on the line.
        const head = v.state.selection.main.head;
        const word = words.find((m) => m.start >= head) ?? words[0];
        const at = v.coordsAtPos(word.start);
        if (at) setMenu({ x: at.left, y: at.bottom, word });
        break;
      }
      default:
        if (action.startsWith("punct_")) insertAtCursor(view.current, PUNCTUATIONS[Number(action.slice(6))], 1);
        if (action.startsWith("use_")) {
          const k = Number(action.slice(4));
          const use = document.querySelector<HTMLElement>(`.side-col [data-use="${k}"]`);
          if (use) use.click();
          else setNotice(`No suggestion ${k} on this line`);
        }
    }
  };
  const bindings = useBindings();
  const closeFind = () => {
    if (!find.open) return false;
    find.close();
    view.current?.focus();
    return true;
  };
  useEditorKeys(bindings, run, () => view.current?.focus(), closeFind);
  const keyed = (label: string, action: string) => `${label} (${bindings[action]})`;
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
  const imagesToggle = images.data?.length ? (
    <button type="button" className="icon" aria-label="Images" title="Images"
      aria-pressed={!imagesCollapsed} onClick={() => saveSetting("images_collapsed", !imagesCollapsed)}><Picture /></button>
  ) : null;
  const chapterMenu = (withLines: boolean) => (
    <Menu label="⋯" buttonLabel="Chapter actions"
      onPointerDown={() => { pendingSelection.current = window.getSelection()?.toString().trim() ?? ""; }}>
      {(close) => ([
        ["Edit source", () => void leave(`/documents/${id}/source`)],
        ["Split chapter", () => void leave(`/documents/${id}/split`)],
        ...(withLines ? [[keyed("Go to line…", "go_to_line"), () => run("go_to_line")] as const] : []),
        ["Series glossary", () => void leave(`/series/${seriesId}?tab=glossary`)],
        ...(withLines ? [[keyed("Add glossary phrase…", "add_phrase"), () => run("add_phrase")] as const] : []),
        ["Series tools", () => void leave(`/series/${seriesId}?tab=tools`)],
        ...(withLines ? [[keyed("Keyboard shortcuts", "key_help"), () => setShowKeys(true)] as const] : []),
      ] as const).map(([text, act]) => (
        <button key={text} type="button" role="menuitem"
          onClick={() => { close(); act(); pendingSelection.current = ""; }}>{text}</button>
      ))}
    </Menu>
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
      .map((n) => ({ line_number: n, translated_text: ed.texts[n] ?? "" }))].sort((a, b) => a.line_number - b.line_number);
    void copyText(all.map((e) => `Line ${e.line_number + 1}\n${e.translated_text}`).join("\n\n"))
      .then((ok) => { if (!ok) setNotice("Could not copy the text"); });
  };
  const restoredNotice = ed.restored
    ? `Restored ${ed.restored} unsaved ${ed.restored === 1 ? "line" : "lines"} from earlier in this tab`
    : null;
  const leaveDialog = asking && (
    <ConfirmDialog title="Leave with unsaved lines?" danger confirmLabel="Leave anyway"
      message={<p>{linesText(asking.lines)} could not be saved: {asking.error} The text is kept in this tab and sent again when you reopen this chapter here. Closing the tab loses it.</p>}
      onConfirm={goAnyway} onClose={stay} />
  );
  const statusBar = (line: number | null, phraseText: string | null, tools: ReactNode) => (
    <StatusBar crumbs={crumbs} line={line} total={lines.length}
      translated={stats.done} lineCount={stats.total} percent={stats.percent} words={stats.words}
      phrase={phraseText} save={barSave} unsavedLines={barSave === ed.save ? unsavedLines : []}
      permanent={ed.savePermanent || Boolean(missingText)}
      onRetry={() => void ed.store.flush()} onCopy={copyUnsaved}
      notice={waiting ? "Leaving once saved. Esc to stay." : restoredNotice ?? notice} spellAvailable={spell.available}
      onLeave={(to) => void leave(to)}
      nav={listed && <ChapterNav doc={listed} chapters={chapters} prevKey={bindings.prev_chapter} nextKey={bindings.next_chapter}
        onGo={(d) => void leave(`/documents/${d.id}`)} />}
      tools={tools} />
  );
  const chapterEnd = (
    <ChapterEnd doc={listed} next={chapters.next} seriesId={seriesId} total={stats.total} done={stats.done}
      words={stats.words} firstLeft={firstLeft} onJump={goToLine} onLeave={(to) => void leave(to)} />
  );

  if (!rows.some((r) => r.kind === "line")) {
    // an illustration-only or empty chapter still shows its images and the way on
    if (images.isPending) return <main />;
    const only = images.data?.length ? "has only images, no source text" : "has no source text yet";
    return (
      <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
        <StickyTop>{statusBar(null, null, <>{imagesToggle}{imagesToggle && <span className="sb-divider" aria-hidden="true" />}{chapterMenu(false)}</>)}</StickyTop>
        {leaveDialog}
        <main className="editor">
          <p>This chapter {only}. <Link to={`/documents/${id}/source`}>Edit source</Link></p>
          {(images.data ?? []).map((image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} />)}
          {chapterEnd}
        </main>
      </div>
    );
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} historyKey={`${id}:${n}`} value={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} autoFocus={!find.stepped.current} onContextMenu={onContextMenu} />
  );
  const useText = (t: string) => {
    if ((ed.texts[n] ?? "") && ed.texts[n] !== t) setNotice(`Replaced line ${n + 1}. Ctrl+Z brings it back`);
    // Through the view, so the replaced translation is one Ctrl+Z away.
    if (view.current) replaceDoc(view.current, t);
    else ed.setText(n, t);
  };
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <h1 className="visually-hidden">{shownTitle(data.document)}</h1>
      <div role="status" className="visually-hidden">Line {n + 1} of {lines.length}</div>
      <StickyTop>
      {statusBar(n + 1, ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null, <>
          <ReadingSwitch mode={mode} onChange={setMode} disabled={!readings.available} title={readings.message} />
          <span className="sb-divider" aria-hidden="true" />
          <button type="button" className="icon" aria-label="Glossary ruby" title={keyed("Glossary ruby", "toggle_glossary_ruby")}
            aria-pressed={glossaryRuby} onClick={() => saveSetting("glossary_ruby", !glossaryRuby)}><Ruby /></button>
          <button type="button" className="icon" aria-label="Translation memory" title={keyed("Translation memory", "toggle_tm")}
            aria-pressed={tmVisible} onClick={() => saveSetting("tm_visible", !tmVisible)}><Memory /></button>
          <button type="button" className="icon" aria-label="Machine translation" title={keyed("Machine translation", "toggle_mt")}
            aria-pressed={mtVisible} onClick={() => saveSetting("mt_visible", !mtVisible)}><Translate /></button>
          {imagesToggle}
          <span className="sb-divider" aria-hidden="true" />
          {chapterMenu(true)}
        </>)}
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
          renderImage={(image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} />} />
        {chapterEnd}
        <JumpBack active={ed.active} untranslated={firstLeft} onActivate={goToLine} onReturn={returnToActive} />
      </div>
      {(tmVisible || mtVisible) && (
        <div className="side-col">
          {tmVisible && <TmPanel documentId={id} lineNumber={n} onUse={useText} slots={slots} bindings={bindings} />}
          {mtVisible && <MtPanels documentId={id} lineNumber={n} translated={Boolean(ed.texts[n])} onUse={useText}
            slots={slots} bindings={bindings} />}
        </div>
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
