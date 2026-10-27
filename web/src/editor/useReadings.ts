import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { api, call } from "../api/client";
import { authorRuby, generatedRuby, type ReadingMode, type Ruby } from "./ruby";

/**
 * MeCab readings for one line's shown text. `ruby` is the complete list to draw (generated plus author ruby in
 * the mode's script), or undefined while the aid is off, the text is empty or the tokens have not arrived, so
 * the card falls back to its plain author ruby. The query key holds the text, so a late answer for a line the
 * reader has left is never used for another line. `available` / `message` are the latest answer's.
 */
/** The API refuses longer text (422); such a line gets no readings. */
const MAX_READING_CHARS = 5000;

export function useReadings(text: string, mode: ReadingMode): { ruby: Ruby[] | undefined; available: boolean; message: string } {
  const q = useQuery({
    queryKey: ["readings", text],
    queryFn: ({ signal }) => call(api.POST("/readings", { body: { text }, signal })),
    enabled: mode !== "off" && text !== "" && text.length <= MAX_READING_CHARS,
    staleTime: Infinity,
    retry: false,
  });
  const data = q.data;
  const ruby = useMemo(
    () => (mode === "off" || text === "" || !data ? undefined : generatedRuby(text, data.tokens, mode, authorRuby(text))),
    [data, text, mode],
  );
  // The last answer's availability holds until another answer arrives, so moving to a line not yet asked
  // about does not flip the switch back on.
  const known = useRef({ available: true, message: "" });
  if (data) known.current = { available: data.available, message: data.message ?? "" };
  return { ruby, ...known.current };
}
