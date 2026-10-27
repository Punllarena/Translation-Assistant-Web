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

/** `disabled` (MeCab missing) turns off the reading choices; Off always stays usable. */
export default function ReadingSwitch({ mode, onChange, disabled, title }: Props) {
  return (
    <span role="group" aria-label="Reading aid" title={disabled ? title : undefined}>
      {CHOICES.map((c) => (
        <button key={c.mode} type="button" aria-pressed={mode === c.mode} aria-label={c.label}
          disabled={disabled && c.mode !== "off"} onClick={() => onChange(c.mode)}>{c.text}</button>
      ))}
    </span>
  );
}
