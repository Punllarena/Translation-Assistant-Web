import { useEffect, useState } from "react";
import { useBlocker } from "react-router";
import GlossaryTable from "../settings/GlossaryTable";
import WordList from "../settings/WordList";

/** The series' glossary and spellcheck dictionary; guards unsaved glossary edits. */
export default function SeriesGlossary({ seriesId }: { seriesId: number }) {
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search)
    // a sign-out redirect must not be held up
    && !nextLocation.pathname.startsWith("/login"));
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Discard unsaved glossary edits?")) blocker.proceed();
    else blocker.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-ask when the state changes
  }, [blocker.state]);
  return (
    <>
      <GlossaryTable seriesId={seriesId} onDirty={setDirty} />
      <WordList path={{ seriesId }} title="Series dictionary" hint="Accepted by spellcheck in this series only." />
    </>
  );
}
