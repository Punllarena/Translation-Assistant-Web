import { useEffect, useRef, useState, type FormEvent } from "react";

export default function PhraseDialog({ initial, onSave, onClose }: {
  initial: string; onSave(phrase: string, translation: string): Promise<void>; onClose(): void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await onSave(String(f.get("phrase")), String(f.get("translation")));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the phrase");
    }
  };
  return (
    <dialog ref={ref} onClose={onClose} aria-label="Add a glossary phrase">
      <form className="stack" onSubmit={submit}>
        <label>Source phrase <input name="phrase" defaultValue={initial} required autoFocus /></label>
        <label>Translation <input name="translation" required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="toolbar">
          <button>Add</button>
          <button type="button" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </dialog>
  );
}
