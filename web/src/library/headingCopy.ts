import type { Schemas } from "../api/client";

export type Marker = Schemas["Marker"];
export type RegroupCounts = Schemas["RegroupCounts"];
export type HeadingMode = "all" | "marker" | "off";

const n = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

export const optionLabel = (m: Marker) =>
  `Only headings starting with ${m.marker} (${n(m.headings, "heading", "headings")})`;

export function regroupMessage(c: RegroupCounts): string {
  const head = `Creates ${n(c.volumes_created, "volume", "volumes")} and moves ${n(c.chapters_moved, "chapter", "chapters")}.`;
  return c.volumes_emptied > 0
    ? `${head} ${n(c.volumes_emptied, "volume", "volumes")} will be left empty; they're kept so switching back finds them.`
    : head;
}

/** The select's value: "all", "off" or "marker:<char>". */
export const encode = (mode: HeadingMode, marker: string) => (mode === "marker" ? `marker:${marker}` : mode);

export function decode(value: string): { mode: HeadingMode; marker: string } {
  if (value.startsWith("marker:")) return { mode: "marker", marker: value.slice("marker:".length) };
  return { mode: value === "off" ? "off" : "all", marker: "" };
}
