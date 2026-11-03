/** The card number the user types (1-based, the number on the line cards) as the stored
 *  anchor: an image anchored at n sits before the line numbered n (0-based). A blank or
 *  unreadable entry means the end of the chapter (the server clamps the large value). */
export const END = Number.MAX_SAFE_INTEGER;

export function anchorFromCardNumber(text: string): number {
  const n = Number(text.trim());
  return text.trim() !== "" && Number.isInteger(n) && n >= 1 ? n - 1 : END;
}

/** The card number shown for a stored anchor, "" when it is past the last line. */
export function cardNumberFromAnchor(anchor: number, lineCount: number): string {
  return anchor >= lineCount ? "" : String(anchor + 1);
}
