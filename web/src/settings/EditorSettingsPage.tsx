import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import PageHeader from "../ui/PageHeader";
import WordList from "./WordList";
import { DEFAULT_PARSE_CHARS } from "./parseChars";

/** Settings → Editor: parse characters, the EPUB translator credit and the account dictionary. */
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
  const saveTranslator = useMutation({
    mutationFn: (epub_translator: string) => call(api.PUT("/settings", { body: { epub_translator } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const stored = settings.data?.parse_chars;
  const current = typeof stored === "string" ? stored : DEFAULT_PARSE_CHARS;
  const storedTranslator = settings.data?.epub_translator;
  const translator = typeof storedTranslator === "string" ? storedTranslator : "";
  const error = settings.error?.message ?? save.error?.message ?? saveTranslator.error?.message;
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
      {settings.data && (
        <form
          key={`translator:${translator}`}
          className="panel sec parse-form"
          onSubmit={(e) => {
            e.preventDefault();
            saveTranslator.mutate((new FormData(e.currentTarget).get("epub_translator") as string).trim());
          }}
        >
          <label className="field">
            <span>Translator credit</span>
            <input name="epub_translator" defaultValue={translator} aria-describedby="translator-hint" />
          </label>
          <button type="submit" disabled={saveTranslator.isPending}>Save</button>
          <p id="translator-hint" className="hint">
            Printed as "Translated by …" in exported EPUBs. A volume's own Translator field wins.
          </p>
        </form>
      )}
      <WordList path="/words" title="Dictionary" hint="Accepted by spellcheck in every series." />
    </main>
  );
}
