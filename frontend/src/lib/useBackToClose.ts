"use client";

import { useEffect, useRef } from "react";

/**
 * Make the browser Back button DISMISS the topmost open overlay instead of
 * navigating away from the deckbuilder (Archidekt/Moxfield-style).
 *
 * Mechanism:
 *  - When `anyOverlayOpen` transitions false -> true we push ONE history entry
 *    (`history.pushState`) so there's a "dummy" state to pop. A ref guards
 *    against pushing more than one entry while overlays remain open (rapid
 *    opens of multiple panels don't stack multiple entries).
 *  - A `popstate` listener fires when the user hits Back. If any overlay is
 *    open at that moment, we call `closeAll()` (consuming the pushed entry) and
 *    the user STAYS on the page. If nothing is open, we don't interfere and
 *    Back navigates normally.
 *  - When overlays close by other means (Esc, close buttons), we pop our own
 *    pushed entry back off so history stays clean and the next Back is normal.
 *
 * `closeAll` MUST be a stable callback (wrap in useCallback at the call site).
 */
export function useBackToClose(anyOverlayOpen: boolean, closeAll: () => void) {
  // True while we own a pushed "overlay" history entry.
  const pushedRef = useRef(false);
  // Latest values, read inside the popstate listener without re-subscribing.
  const openRef = useRef(anyOverlayOpen);
  const closeRef = useRef(closeAll);
  // Set true while WE are the ones calling history.back() to clean up, so the
  // resulting popstate doesn't get treated as a user-initiated dismissal.
  const selfPoppingRef = useRef(false);

  openRef.current = anyOverlayOpen;
  closeRef.current = closeAll;

  // Push a dummy entry on open; clean it up when overlays close by other means.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (anyOverlayOpen && !pushedRef.current) {
      pushedRef.current = true;
      window.history.pushState({ ddOverlay: true }, "");
    } else if (!anyOverlayOpen && pushedRef.current) {
      // Overlays were closed by some non-Back means (Esc / close button).
      // Pop our own dummy entry so history doesn't accumulate; mark it as a
      // self-pop so the popstate handler ignores it.
      pushedRef.current = false;
      selfPoppingRef.current = true;
      window.history.back();
    }
  }, [anyOverlayOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => {
      if (selfPoppingRef.current) {
        // This popstate is our own cleanup back() — swallow it.
        selfPoppingRef.current = false;
        return;
      }
      if (openRef.current) {
        // User hit Back with overlays open: consume it by closing them. Our
        // dummy entry has already been popped by the browser, so clear the flag.
        pushedRef.current = false;
        closeRef.current();
      }
      // Otherwise: nothing open — let the navigation proceed normally.
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
}
