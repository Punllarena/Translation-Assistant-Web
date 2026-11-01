/** Copy through a hidden textarea, for contexts where `navigator.clipboard` is missing or refuses. */
function legacyCopy(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
  const prev = document.activeElement as HTMLElement | null;
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
    prev?.focus?.();
  }
}

/** Copy `text`, through the async clipboard where the origin allows it. */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // a plain-http origin (a LAN address) has the API but refuses it
    }
  }
  return legacyCopy(text);
}
