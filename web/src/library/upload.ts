import { ApiError, errorMessage } from "../api/client";

/** POST (or PUT) multipart form data (the generated client types JSON bodies only). */
export async function postForm<T>(path: string, form: FormData, method: "POST" | "PUT" = "POST"): Promise<T> {
  const response = await fetch(`/api${path}`, { method, body: form });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 413 ? "File too large" : errorMessage(await response.json().catch(() => null)),
    );
  }
  return response.json() as Promise<T>;
}
