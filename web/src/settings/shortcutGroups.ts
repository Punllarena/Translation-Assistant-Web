import type { Action } from "../editor/keymap";

export interface ActionGroup { title: string; actions: Action[] }

const TITLES = ["Moving between lines", "Phrases and tools", "Insert characters", "Text size"] as const;
const LINES = new Set(["save_next", "next", "next_alt", "prev", "prev_alt", "next_untranslated", "first", "go_to_line"]);
const SIZE = new Set(["font_larger", "font_smaller"]);

function titleOf(key: string): (typeof TITLES)[number] {
  if (LINES.has(key)) return "Moving between lines";
  if (key.startsWith("punct_")) return "Insert characters";
  if (SIZE.has(key)) return "Text size";
  return "Phrases and tools";
}

/** The Shortcuts page's sections, each in ACTIONS order; empty sections are dropped. */
export function groupActions(actions: Action[]): ActionGroup[] {
  return TITLES
    .map((title) => ({ title, actions: actions.filter((a) => titleOf(a.key) === title) }))
    .filter((g) => g.actions.length > 0);
}
