/** Which `use_N` action picks which suggestion. Translation memory always holds 1 and 2
 *  (the desktop's two matches); MeCab and JParser have no Use button, so they take no slot.
 *  A backend that is enabled but slow keeps its number, so nothing moves under the user. */
export function assignSlots(enabled: string[]): { tm: [1, 2]; backends: Record<string, number> } {
  const backends: Record<string, number> = {};
  let next = 3;
  for (const name of enabled) {
    if (name === "mecab" || name === "jparser") continue;
    backends[name] = next++;
  }
  return { tm: [1, 2], backends };
}
