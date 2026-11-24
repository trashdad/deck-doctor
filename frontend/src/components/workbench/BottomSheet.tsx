"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDialogFocus } from "@/hooks/useDialogFocus";

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
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => setMounted(true), []);
  // aria-modal is a promise: focus moves in, Tab stays in, focus returns on close (review F-12).
  useDialogFocus(panelRef, open && mounted);
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
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label={label}
        data-testid={testid}
        data-tall={tall ? "true" : undefined}
        className="dd-sheet outline-none"
        // The sheet sits bottomOffset px above the viewport bottom; never let it run off the top (review F-12).
        style={{
          bottom: bottomOffset,
          height: `min(${tall ? "90vh" : "60vh"}, calc(100vh - ${bottomOffset}px))`,
          maxHeight: `calc(100vh - ${bottomOffset}px)`,
        }}
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
