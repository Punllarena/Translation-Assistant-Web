import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import PageHeader from "../ui/PageHeader";
import WordList from "./WordList";
import { DEFAULT_PARSE_CHARS } from "./parseChars";

/** Settings → Editor: parse characters and the account dictionary. */
export default function EditorSettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const save = useMutation({
    mutationFn: (parse_chars: string) => call(api.PUT("/settings", { body: { parse_chars } })),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ["settings"] }),
      queryClient.invalidateQueries({ queryKey: ["document"] }),
    ]),
  });
  const stored = settings.data?.parse_chars;
  const current = typeof stored === "string" ? stored : DEFAULT_PARSE_CHARS;
  const error = settings.error?.message ?? save.error?.message;
  return (
    <main>
      <PageHeader title="Editor" />
      {error && <p className="error" role="alert">{error}</p>}
      {settings.data && (
        <form
          key={current}
          className="panel sec parse-form"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(new FormData(e.currentTarget).get("parse_chars") as string);
          }}
        >
          <label className="field">
            <span>Parse characters</span>
            <input name="parse_chars" className="mono" defaultValue={current} aria-describedby="parse-hint" />
          </label>
          <button type="submit" disabled={save.isPending}>Save</button>
          <p id="parse-hint" className="hint">Characters that end a phrase for Next phrase and Previous phrase.</p>
        </form>
      )}
      <WordList path="/words" title="Dictionary" hint="Accepted by spellcheck in every series." />
    </main>
  );
}
