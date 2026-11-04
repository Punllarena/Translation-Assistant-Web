import { useId } from "react";
import Menu from "../ui/Menu";
import type { ReadingMode } from "./ruby";

const CHOICES: { mode: ReadingMode; text: string; label: string }[] = [
  { mode: "off", text: "Off", label: "Readings off" },
  { mode: "hiragana", text: "あ", label: "Hiragana readings" },
  { mode: "katakana", text: "ア", label: "Katakana readings" },
  { mode: "romaji", text: "Abc", label: "Romaji readings" },
];

interface Props {
  mode: ReadingMode;
  onChange: (mode: ReadingMode) => void;
  disabled?: boolean;
  title?: string;
}

/** One button per mode while there is room for them; below 40rem (`editor.css`) the same four
 *  are one labelled menu button, so the reading choices never shrink to a row of bare glyphs.
 *  `disabled` (MeCab missing) turns off the reading choices; Off always stays usable. The reason
 *  shows in the group's title on a wide screen and as its own line in the narrow menu. */
export default function ReadingSwitch({ mode, onChange, disabled, title }: Props) {
  const id = useId();
  const reason = disabled ? title : undefined;
  const current = CHOICES.find((c) => c.mode === mode) ?? CHOICES[0];
  return (
    <span role="group" aria-label="Reading aid" title={reason} aria-describedby={reason ? id : undefined}>
      <span className="reading-label" aria-hidden="true">Readings</span>
      <span className="reading-modes">
        {CHOICES.map((c) => (
          <button key={c.mode} type="button" aria-pressed={mode === c.mode} aria-label={c.label}
            disabled={disabled && c.mode !== "off"} onClick={() => onChange(c.mode)}>{c.text}</button>
        ))}
      </span>
      <span className="reading-menu">
        <Menu buttonLabel={`Readings: ${current.label}`}
          label={<><span>Readings: {current.text}</span> <span aria-hidden="true">▾</span></>}>
          {(close) => (
            <>
              {CHOICES.map((c) => (
                <button key={c.mode} type="button" role="menuitemradio" aria-checked={mode === c.mode}
                  disabled={disabled && c.mode !== "off"}
                  onClick={() => { close(); onChange(c.mode); }}>{c.label}</button>
              ))}
              {reason && <p className="menu-label">{reason}</p>}
            </>
          )}
        </Menu>
      </span>
      {reason && <span id={id} className="visually-hidden">{reason}</span>}
    </span>
  );
}
