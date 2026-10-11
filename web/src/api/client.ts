import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const api = createClient<paths>({ baseUrl: "/api" });

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI's error body as one readable line: a string detail, or its validation list. */
export function errorMessage(body: unknown): string {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const where = (d.loc ?? []).slice(1).join(".");
        return where ? `${where}: ${d.msg}` : String(d.msg);
      })
      .join("; ");
  }
  return "request failed";
}

/** Await an openapi-fetch call: its data, or an ApiError carrying the status. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) throw new ApiError(response.status, errorMessage(error));
  return data as T;
}
