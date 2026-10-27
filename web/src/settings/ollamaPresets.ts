export type PresetKey = "small" | "medium" | "large" | "custom";

/** Mirrors api/ollama/prefs.py; chunk 0 means the whole chapter. */
export const PRESETS: Record<PresetKey, { label: string; chunk: number; context: number }> = {
  small: { label: "Small CPU (≈2B)", chunk: 12, context: 5 },
  medium: { label: "Medium (4–8B)", chunk: 25, context: 10 },
  large: { label: "Large / GPU", chunk: 0, context: 0 },
  custom: { label: "Custom", chunk: 12, context: 5 },
};

/** The preset whose numbers these are, else "custom". */
export function presetFor(chunk: number, context: number): PresetKey {
  for (const k of ["small", "medium", "large"] as const) {
    if (PRESETS[k].chunk === chunk && PRESETS[k].context === context) return k;
  }
  return "custom";
}
