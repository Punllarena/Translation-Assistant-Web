import type { EditorView } from "@codemirror/view";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router";
import SpellMenu from "./SpellMenu";
import { useSpell } from "./useSpell";
import { api, call, type Schemas } from "../api/client";
import type { Misspelling } from "./LineCard";
import CardList from "./CardList";
import CodeEditor, { insertAtCursor, setMarks } from "./CodeEditor";
import FindBar from "./FindBar";
import ImageCard from "./ImageCard";
import { PUNCTUATIONS } from "./keymap";
import { advanceParse, retreatParse } from "./parse";
import { buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, nextContent, prevContent, progress } from "./rows";
import StatusBar from "./StatusBar";
import { useEditor } from "./useEditor";
import { useFind } from "./useFind";
import { useBindings, useEditorKeys } from "./useEditorKeys";

type Data = Schemas["DocumentLines"];

export default function Editor({ id, data, onProfile }: { id: number; data: Data; onProfile(id: number | null): void }) {
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
  const imagesCollapsed = Boolean(settings.data?.images_collapsed);
  const stats = useMemo(() => progress(lines, ed.texts), [lines, ed.texts]);
  const onReady = useCallback((v: EditorView | null) => { view.current = v; }, []);
  const current = lines[ed.active];
  const queryClient = useQueryClient();
  const setFont = (px: number) => {
    const size = Math.max(12, Math.min(32, px));
    queryClient.setQueryData(["settings"], { ...settings.data, editor_font_px: size });
    void call(api.PUT("/settings", { body: { editor_font_px: size } })).catch(() => {});
  };
  const edRef = useRef(ed);
  edRef.current = ed;
  const find = useFind(rows, ed.texts, ed.active, ed.activate);
  const { hit } = find;
  const activate = useCallback((i: number | null) => { find.stepped.current = false; edRef.current.activate(i); }, [find.stepped]);
  const profileId = data.profile?.id ?? null;
  const spell = useSpell(profileId, lines.map((l) => ed.texts[l.line_number] ?? ""));
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  const [menu, setMenu] = useState<{ x: number; y: number; word: Misspelling } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const addWord = async (word: string) => {
    if (!profileId) return setNotice("No profile to add words to");
    word = word.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
    if (!word || /\s/.test(word)) return setNotice("Select a single word first");
    if (word.includes("/")) return setNotice("Words with / can't be added");
    try {
      await call(api.PUT("/profiles/{profile_id}/words/{word}", { params: { path: { profile_id: profileId, word } } }));
      spell.forget();
      setNotice(`Added \u201c${word}\u201d to the dictionary`);
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
    if (!lines[at]) return;
    switch (action) {
      case "save_next":
        void ed.store.flush();
        activate(nextContent(lines, at));
        break;
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
      case "next_untranslated":
        // desktop: only from a line that already has a translation
        if (ed.texts[lines[at].line_number]) activate(firstUntranslated(lines, ed.texts));
        break;
      case "parse_next":
        ed.setParse((p) => advanceParse(p, lines[at].sentences.length));
        break;
      case "parse_prev":
        ed.setParse((p) => retreatParse(p, lines[at].replaced));
        break;
      case "go_to_line": {
        const answer = window.prompt(`Go to line (1\u2013${lines.length})`);
        const k = Number(answer);
        if (answer && Number.isInteger(k)) activate(lineAtOrAfter(lines, k));
        break;
      }
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
          void addWord(v.state.sliceDoc(from, to).trim());
        }
        break;
      }
      case "find":
        find.show();
        break;
      default:
        if (action.startsWith("punct_")) insertAtCursor(view.current, PUNCTUATIONS[Number(action.slice(6))], 1);
    }
  };
  useEditorKeys(useBindings(), run);
  // Every hook stays above this early return; later tasks add theirs here too and read
  // `current?.` (it is undefined for a chapter with no lines).

  if (!rows.some((r) => r.kind === "line")) {
    return <main><p>This chapter has no source text yet. <Link to={`/documents/${id}/source`}>Edit source</Link></p></main>;
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} value={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} autoFocus={!find.stepped.current} onContextMenu={onContextMenu} />
  );
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <StatusBar title={data.document.title} line={n + 1} total={lines.length}
        percent={stats.percent} words={stats.words}
        phrase={ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null}
        save={ed.save} onRetry={() => void ed.store.flush()} notice={notice}
        extra={<>
          <select aria-label="Profile" value={profileId ?? ""} onChange={(e) => onProfile(e.target.value ? Number(e.target.value) : null)}>
            {!profileId && <option value="">No profile</option>}
            {(profiles.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Link to={`/documents/${id}/source`}>Edit source</Link>
          <Link to={`/documents/${id}/split`}>Split</Link>
          {!spell.available && <span className="muted">Spellcheck unavailable</span>}
          {images.data?.length ? (
            <button onClick={() => {
              queryClient.setQueryData(["settings"], { ...settings.data, images_collapsed: !imagesCollapsed });
              void call(api.PUT("/settings", { body: { images_collapsed: !imagesCollapsed } })).catch(() => {});
            }}>{imagesCollapsed ? "Show images" : "Collapse images"}</button>
          ) : null}
        </>} />
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={find.at} total={find.total}
          onNeedle={find.setNeedle} onStep={find.step}
          onClose={() => { find.close(); view.current?.focus(); }} />
      )}
      <div className="editor">
        <CardList rows={rows} active={ed.active} parse={ed.parse} texts={ed.texts}
          onActivate={activate} editor={editor} highlight={hit}
          misspelled={spell.misspelled}
          renderImage={(image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} />} />
      </div>
      {menu && <SpellMenu {...menu} onClose={closeMenu} onAdd={() => { void addWord(menu.word.word); closeMenu(); }}
        onPick={(s) => {
          const v = view.current;
          const { start, end, word } = menu.word;
          if (v && end <= v.state.doc.length && v.state.sliceDoc(start, end) === word) v.dispatch({ changes: { from: start, to: end, insert: s } });
          closeMenu();
        }} />}
    </div>
  );
}
