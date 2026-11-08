"use client";

import { useEffect, useState } from "react";

/** Tailwind `lg` breakpoint — the plan's desktop/stacked boundary (§4.1, §4.9). */
export const DESKTOP_QUERY = "(min-width: 1024px)";

/**
 * True at ≥ 1024 px. Starts false (SSR + first client paint) and settles in an
 * effect, so a component that must exist only once (rail, stats) is never
 * mounted twice for the two layouts.
 */
export function useDesktop(): boolean {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY);
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}
