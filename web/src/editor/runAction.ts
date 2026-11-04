import type { EditorView } from "@codemirror/view";
import type { ReactNode, RefObject } from "react";
import type { Misspelling } from "./LineCard";
import { insertAtCursor } from "./CodeEditor";
import { PUNCTUATIONS } from "./keymap";
import { advanceParse, retreatParse } from "./parse";
import { firstContent, firstUntranslated, nextContent, prevContent, type Line } from "./rows";
import type { ReadingMode } from "./ruby";
import type { useEditor } from "./useEditor";

const READING_ORDER: ReadingMode[] = ["off", "hiragana", "katakana", "romaji"];

/** Everything one bound key needs; the editor builds it from the same values it renders. */
export interface RunContext {
  ed: ReturnType<typeof useEditor>;
  lines: Line[];
  phrase: string | null;
  view: RefObject<EditorView | null>;
  pendingSelection: RefObject<string>;
  chapters: { prev: { id: number } | null; next: { id: number } | null };
  mode: ReadingMode;
  readingsAvailable: boolean;
  tmVisible: boolean;
  mtVisible: boolean;
  glossaryRuby: boolean;
  fontPx: number;
  setWantEnd(value: boolean): void;
  setNotice(text: ReactNode): void;
  setPhrase(value: string | null): void;
  setGoTo(value: string | null): void;
  setGoToError(value: string | null): void;
  setFont(px: number): void;
  setMode(mode: ReadingMode): void;
  setShowKeys(value: boolean): void;
  setMenu(menu: { x: number; y: number; word: Misspelling }): void;
  saveSetting(key: string, value: unknown): void;
  addWord(word: string, scope: "series" | "all"): void;
  activate(index: number | null): void;
  showFind(): void;
  misspelled(text: string): Misspelling[];
  leave(to: string): Promise<void> | void;
}

/** The editor's key actions (the desktop `_handle_key` table), one switch. Kept out of the
 *  render tree so Editor.tsx stays a page: it reads the editor, the line and the settings it
 *  is given and runs one action. */
export function runAction(action: string, p: RunContext): void {
  const at = p.ed.active;
  if (!p.lines[at] || p.phrase !== null) return;
  switch (action) {
    case "save_next": {
      void p.ed.store.flush();
      const next = nextContent(p.lines, at);
      if (next !== null) {
        p.activate(next);
        break;
      }
      // The last line: the way on is the end card, whose button may still be loading.
      p.setWantEnd(true);
      break;
    }
    case "next":
    case "next_alt":
      p.activate(nextContent(p.lines, at));
      break;
    case "prev":
    case "prev_alt":
      p.activate(prevContent(p.lines, at));
      break;
    case "first":
      p.activate(firstContent(p.lines));
      break;
    case "next_untranslated": {
      // desktop: only from a line that already has a translation
      if (!p.ed.texts[p.lines[at].line_number]) {
        p.setNotice("This line has no translation yet");
        break;
      }
      const next = firstUntranslated(p.lines, p.ed.texts);
      if (next === null) p.setNotice("No untranslated lines left");
      else p.activate(next);
      break;
    }
    case "parse_next":
      p.ed.setParse((n) => advanceParse(n, p.lines[at].sentences.length));
      break;
    case "parse_prev":
      p.ed.setParse((n) => retreatParse(n, p.lines[at].replaced));
      break;
    case "go_to_line":
      p.setGoToError(null);
      p.setGoTo("");
      break;
    case "font_larger":
      p.setFont(p.fontPx + 1);
      break;
    case "font_smaller":
      p.setFont(p.fontPx - 1);
      break;
    case "add_word": {
      const v = p.view.current;
      if (v) {
        const { from, to } = v.state.selection.main;
        p.addWord(v.state.sliceDoc(from, to).trim(), "series");
      }
      break;
    }
    case "add_phrase":
      p.setPhrase(p.pendingSelection.current || window.getSelection()?.toString().trim() || "");
      break;
    case "find":
      p.showFind();
      break;
    case "next_chapter":
      if (p.chapters.next) void p.leave(`/documents/${p.chapters.next.id}`);
      break;
    case "prev_chapter":
      if (p.chapters.prev) void p.leave(`/documents/${p.chapters.prev.id}`);
      break;
    case "toggle_tm":
      p.saveSetting("tm_visible", !p.tmVisible);
      break;
    case "toggle_mt":
      p.saveSetting("mt_visible", !p.mtVisible);
      break;
    case "toggle_glossary_ruby":
      p.saveSetting("glossary_ruby", !p.glossaryRuby);
      break;
    case "cycle_reading":
      if (p.readingsAvailable) {
        p.setMode(READING_ORDER[(READING_ORDER.indexOf(p.mode) + 1) % READING_ORDER.length]);
      }
      break;
    case "key_help":
      p.setShowKeys(true);
      break;
    case "retry_save":
      void p.ed.store.flush();
      break;
    case "spell_open": {
      const v = p.view.current;
      if (!v) break;
      const words = p.misspelled(v.state.doc.toString());
      if (!words.length) {
        p.setNotice("No misspelled words on this line");
        break;
      }
      // The word under or after the caret, else the first on the line.
      const head = v.state.selection.main.head;
      const word = words.find((m) => m.start >= head) ?? words[0];
      const spot = v.coordsAtPos(word.start);
      if (spot) p.setMenu({ x: spot.left, y: spot.bottom, word });
      break;
    }
    default:
      if (action.startsWith("punct_")) insertAtCursor(p.view.current, PUNCTUATIONS[Number(action.slice(6))], 1);
      if (action.startsWith("use_")) {
        const k = Number(action.slice(4));
        const use = document.querySelector<HTMLElement>(`.side-col [data-use="${k}"]`);
        if (use) use.click();
        else p.setNotice(`No match for suggestion ${k} on this line`);
      }
  }
}
