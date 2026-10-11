const MAX_TEXT_CHARS = 100_000;

/** Request batches within the /spell/check caps (200 texts, 200,000 chars in total). */
export function spellBatches(texts: string[], maxTexts = 200, maxChars = 200_000): string[][] {
  const batches: string[][] = [];
  let batch: string[] = [];
  let chars = 0;
  for (const t of texts) {
    if (!t || t.length > MAX_TEXT_CHARS) continue;
    if (batch.length && (batch.length === maxTexts || chars + t.length > maxChars)) {
      batches.push(batch);
      batch = [];
      chars = 0;
    }
    batch.push(t);
    chars += t.length;
  }
  if (batch.length) batches.push(batch);
  return batches;
}
