const box = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor",
  strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

export const ArrowUp = () => <svg {...box}><path d="M8 13V3M4 7l4-4 4 4" /></svg>;
export const ArrowDown = () => <svg {...box}><path d="M8 3v10M4 9l4 4 4-4" /></svg>;
export const Cross = () => <svg {...box}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
