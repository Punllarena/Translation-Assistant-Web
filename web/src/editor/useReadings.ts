import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, call } from "../api/client";
import { authorRuby, generatedRuby, type ReadingMode, type Ruby } from "./ruby";

/**
 * MeCab readings for one line's shown text. `ruby` is the complete list to draw (generated plus author ruby in
 * the mode's script), or undefined while the aid is off, the text is empty or the tokens have not arrived, so
 * the card falls back to its plain author ruby. The query key holds the text, so a late answer for a line the
 * reader has left is never used for another line.
 */
export function useReadings(text: string, mode: ReadingMode): { ruby: Ruby[] | undefined; available: boolean; message: string } {
  const q = useQuery({
    queryKey: ["readings", text],
    queryFn: ({ signal }) => call(api.POST("/readings", { body: { text }, signal })),
    enabled: mode !== "off" && text !== "",
    staleTime: Infinity,
  });
  const data = q.data;
  const ruby = useMemo(
    () => (mode === "off" || text === "" || !data ? undefined : generatedRuby(text, data.tokens, mode, authorRuby(text))),
    [data, text, mode],
  );
  return { ruby, available: data?.available ?? true, message: data?.message ?? "" };
}
