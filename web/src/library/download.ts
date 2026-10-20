import { ApiError, errorMessage } from "../api/client";

/** Fetch a file and save it under `filename`. Fetched rather than linked so a 409/422 shows as an
 *  error instead of downloading as a JSON file. */
export async function downloadBlob(url: string, filename: string, init?: RequestInit): Promise<void> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(await response.json().catch(() => null)));
  }
  const href = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 0); // after the click has started the download
}
