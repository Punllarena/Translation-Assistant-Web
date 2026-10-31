import { describe, expect, it } from "vitest";
import { ACTIONS } from "../editor/keymap";
import { groupActions } from "./shortcutGroups";

describe("shortcut sections", () => {
  it("puts every action in exactly one section, keeping order", () => {
    const groups = groupActions(ACTIONS);
    expect(groups.map((g) => g.title)).toEqual(["Moving between lines", "Phrases and tools", "Insert characters", "Text size", "Suggestions, chapters and panels"]);
    expect(groups.flatMap((g) => g.actions).map((a) => a.key).sort()).toEqual(ACTIONS.map((a) => a.key).sort());
    expect(groups[0].actions.map((a) => a.key)).toEqual(
      ["save_next", "next", "next_alt", "prev", "prev_alt", "next_untranslated", "first", "go_to_line"]);
    expect(groups[2].actions).toHaveLength(9);
    expect(groups[3].actions.map((a) => a.key)).toEqual(["font_larger", "font_smaller"]);
  });
  it("files an unknown action under Phrases and tools and drops empty sections", () => {
    const extra = { key: "new_thing", label: "New thing", binding: "Ctrl+K" };
    expect(groupActions([extra])).toEqual([{ title: "Phrases and tools", actions: [extra] }]);
  });
});
