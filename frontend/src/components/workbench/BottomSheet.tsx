"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name of the dialog. */
  label: string;
  /** Height of the fixed bar the sheet must sit above (the rail tab bar is 56 px). */
  bottomOffset?: number;
  testid?: string;
  children: ReactNode;
}

/**
 * Generic bottom sheet for < 1024 px (plan §4.9): 60 vh, tap the grab handle
 * for 90 vh, scrim closes, Escape closes. Back is handled by the page's
 * `useBackToClose` (the open flag lives in the UI store).
 */
export function BottomSheet({ open, onClose, label, bottomOffset = 0, testid, children }: BottomSheetProps) {
  const [mounted, setMounted] = useState(false);
  const [tall, setTall] = useState(false);
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!open) {
      setTall(false);
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted || !open) return null;
  return createPortal(
    <>
      <div className="dd-sheet-backdrop" style={{ bottom: bottomOffset }} onPointerDown={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        data-testid={testid}
        data-tall={tall ? "true" : undefined}
        className="dd-sheet"
        style={{ bottom: bottomOffset, height: tall ? "90vh" : "60vh", maxHeight: tall ? "90vh" : "60vh" }}
      >
        <button
          type="button"
          onClick={() => setTall((t) => !t)}
          aria-label={tall ? "Shrink sheet" : "Expand sheet"}
          className="flex h-6 w-full shrink-0 items-center justify-center"
        >
          <span className="h-1 w-10 rounded-full bg-zinc-500/70" aria-hidden="true" />
        </button>
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </div>
    </>,
    document.body,
  );
}
