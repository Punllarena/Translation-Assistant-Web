import { useEffect, useRef, useState } from "react";

/** The timer half of `useDebounced`: `apply` runs once `ms` have passed since the last push,
 *  with only the last value. Pure enough to test without a renderer. */
export function trailingDebounce<T>(ms: number, apply: (value: T) => void) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return {
    push(value: T): void {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        apply(value);
      }, ms);
    },
    cancel(): void {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}

/** `value`, once it has been the same for `ms`. Held-key stepping through the chapter then
 *  speaks once at rest instead of announcing every line it passes. */
export function useDebounced<T>(value: T, ms: number): T {
  const [held, setHeld] = useState(value);
  const box = useRef<ReturnType<typeof trailingDebounce<T>> | null>(null);
  if (box.current === null) box.current = trailingDebounce(ms, setHeld);
  useEffect(() => () => box.current?.cancel(), []);
  useEffect(() => {
    box.current?.push(value);
  }, [value]);
  return held;
}
