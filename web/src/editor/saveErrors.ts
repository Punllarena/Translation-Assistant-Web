import { ApiError } from "../api/client";

export interface SaveFailure {
  message: string;
  /** Trying again cannot help: the same answer will come back. */
  permanent: boolean;
}

/** Why a save failed, in words a translator reads, and whether retrying can help. */
export function saveFailure(e: unknown): SaveFailure {
  if (e instanceof ApiError) {
    if (e.status === 404) return { message: "This chapter no longer exists on the server.", permanent: true };
    if (e.status === 422) return { message: "The server refused this text. It may be too long.", permanent: true };
    if (e.status === 401) return { message: "Your session ended; sign in again and the text is kept.", permanent: false };
    if (e.status === 408 || e.status === 429 || e.status >= 500) {
      return { message: `The server answered ${e.status}.`, permanent: false };
    }
    return { message: `The server refused the save (${e.status}).`, permanent: true };
  }
  if (e instanceof DOMException && e.name === "TimeoutError") {
    return { message: "The server took too long to answer.", permanent: false };
  }
  if (e instanceof TypeError) return { message: "The server can't be reached.", permanent: false };
  return { message: e instanceof Error ? e.message : String(e), permanent: false };
}
