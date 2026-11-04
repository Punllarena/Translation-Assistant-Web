import { useId } from "react";
import type { ReadingMode } from "./ruby";

const CHOICES: { mode: ReadingMode; text: string; label: string }[] = [
  { mode: "off", text: "Off", label: "Readings off" },
  { mode: "hiragana", text: "あ", label: "Hiragana readings" },
  { mode: "katakana", text: "ア", label: "Katakana readings" },
  { mode: "romaji", text: "a", label: "Romaji readings" },
];

interface Props {
  mode: ReadingMode;
  onChange: (mode: ReadingMode) => void;
  disabled?: boolean;
  title?: string;
}

/** `disabled` (MeCab missing) turns off the reading choices; Off always stays usable. The
 *  reason lives in the group's title and a hidden description, not in a standing bar note. */
export default function ReadingSwitch({ mode, onChange, disabled, title }: Props) {
  const id = useId();
  const reason = disabled ? title : undefined;
  return (
    <span role="group" aria-label="Reading aid" title={reason} aria-describedby={reason ? id : undefined}>
      <span className="reading-label" aria-hidden="true">Readings</span>
      {CHOICES.map((c) => (
        <button key={c.mode} type="button" aria-pressed={mode === c.mode} aria-label={c.label}
          disabled={disabled && c.mode !== "off"} onClick={() => onChange(c.mode)}>{c.text}</button>
      ))}
      {reason && <span id={id} className="visually-hidden">{reason}</span>}
    </span>
  );
}
