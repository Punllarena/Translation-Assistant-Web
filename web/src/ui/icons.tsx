const box = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor",
  strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

export const ArrowUp = () => <svg {...box}><path d="M8 13V3M4 7l4-4 4 4" /></svg>;
export const ArrowDown = () => <svg {...box}><path d="M8 3v10M4 9l4 4 4-4" /></svg>;
export const Cross = () => <svg {...box}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
export const Memory = () => <svg {...box}><path d="M3 3.5h10v9H3zM5.5 6.5h5M5.5 9.5h3" /></svg>;
export const Translate = () => <svg {...box}><path d="M2.5 4h6M5.5 2.5V4M7.5 4c-.5 2.5-2.5 4.5-5 5.5M4 6.5c.8 1.4 2 2.4 3.5 3M9 13.5l2.5-6 2.5 6M9.8 11.5h3.4" /></svg>;
export const Picture = () => <svg {...box}><path d="M2.5 3.5h11v9h-11zM2.5 10.5l3-3 3 3 2-2 3 3" /><circle cx="10.5" cy="6" r="1" /></svg>;
