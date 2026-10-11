/** The desktop's nine special-character inserts (main_widget._PUNCTUATIONS). */
export const PUNCTUATIONS = ["「」", "『』", "【】", "…", "〜", "〈〉", "《》", "ー", "♡"];
const PUNCT_NAMES = [
  "single quote", "double quote", "lenticular brackets", "ellipsis", "wave dash",
  "single title brackets", "double title brackets", "long dash", "heart",
];

export interface Action {
  key: string;
  label: string;
  binding: string; // the default
}

/** Every editor action and its default key (desktop _handle_key and the shortcut
 *  registry). All are rebindable. */
export const ACTIONS: Action[] = [
  { key: "save_next", label: "Save and go to the next line", binding: "Enter" },
  { key: "next", label: "Next line", binding: "PageDown" },
  { key: "next_alt", label: "Next line (second key)", binding: "Ctrl+ArrowDown" },
  { key: "prev", label: "Previous line", binding: "PageUp" },
  { key: "prev_alt", label: "Previous line (second key)", binding: "Ctrl+ArrowUp" },
  { key: "next_untranslated", label: "Next untranslated line", binding: "Ctrl+End" },
  { key: "first", label: "First line", binding: "Ctrl+Home" },
  { key: "parse_next", label: "Next phrase", binding: "Ctrl+ArrowRight" },
  { key: "parse_prev", label: "Previous phrase", binding: "Ctrl+ArrowLeft" },
  { key: "go_to_line", label: "Go to line", binding: "Ctrl+G" },
  { key: "find", label: "Find", binding: "Ctrl+F" },
  { key: "add_word", label: "Add the selected word to the dictionary", binding: "Ctrl+J" },
  { key: "font_larger", label: "Larger text", binding: "Ctrl+=" },
  { key: "font_smaller", label: "Smaller text", binding: "Ctrl+-" },
  ...PUNCTUATIONS.map((p, i) => ({
    key: `punct_${i}`,
    label: `Insert ${PUNCT_NAMES[i]} ${p}`,
    binding: `F${i + 1}`,
  })),
];

/** Combinations browsers do not let a page handle. */
export const RESERVED = new Set([
  "Ctrl+N", "Ctrl+Shift+N", "Ctrl+T", "Ctrl+Shift+T", "Ctrl+W", "Ctrl+Shift+W",
  "Ctrl+Tab", "Ctrl+Shift+Tab",
]);

const MODIFIERS = new Set(["Control", "Shift", "Alt", "Meta", "AltGraph", "CapsLock"]);

/** A key press as a binding string, e.g. "Ctrl+Shift+ArrowRight"; null for a bare
 *  modifier. Cmd counts as Ctrl so defaults work on macOS. */
export function bindingOf(
  e: Pick<KeyboardEvent, "key" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">,
): string | null {
  if (MODIFIERS.has(e.key)) return null;
  const key = e.key === " " ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key]
    .filter(Boolean)
    .join("+");
}

/** Each action's binding: the user's override, else the default. */
export function effective(overrides: Record<string, string>): Record<string, string> {
  return Object.fromEntries(ACTIONS.map((a) => [a.key, overrides[a.key] ?? a.binding]));
}

export const actionOf = (bindings: Record<string, string>, binding: string) =>
  Object.keys(bindings).find((k) => bindings[k] === binding);

/** Why `binding` cannot be given to `action`, or null when it can. Checks the effective
 *  map, so an unchanged default counts (the server only sees overrides). */
export function bindingProblem(
  bindings: Record<string, string>,
  action: string,
  binding: string,
): string | null {
  if (RESERVED.has(binding)) return `${binding} is reserved by the browser`;
  const owner = actionOf(bindings, binding);
  if (owner && owner !== action) {
    return `${binding} is already used by "${ACTIONS.find((a) => a.key === owner)?.label ?? owner}"`;
  }
  return null;
}
