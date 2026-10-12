import { ApiError, errorMessage } from "../api/client";

/** POST multipart form data (the generated client types JSON bodies only). */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`/api${path}`, { method: "POST", body: form });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 413 ? "File too large" : errorMessage(await response.json().catch(() => null)),
    );
  }
  return response.json() as Promise<T>;
}
