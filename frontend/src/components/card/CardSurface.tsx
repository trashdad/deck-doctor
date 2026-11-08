"use client";

import { useRef } from "react";
import { useRovingFocus, type RovingOrientation } from "@/hooks/useRovingFocus";

export interface CardSurfaceProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Unique id; CardInteractive children pass the same value as `surfaceId`. */
  id: string;
  /** grid (search), row (piles / commander strip), column (rail lists). */
  orientation?: RovingOrientation;
  label: string;
  children: React.ReactNode;
}

/**
 * A `[data-surface]` host: one Tab stop, arrow keys move between cards
 * (§4.7.4). The preview and the keyboard menu are placed *beside* this box.
 */
export function CardSurface({ id, orientation = "grid", label, children, className, ...rest }: CardSurfaceProps) {
  const ref = useRef<HTMLDivElement>(null);
  const roving = useRovingFocus(ref, { orientation });
  return (
    <div
      ref={ref}
      data-surface={id}
      role="group"
      aria-label={label}
      className={className}
      onKeyDown={roving.onKeyDown}
      onFocusCapture={roving.onFocusCapture}
      {...rest}
    >
      {children}
    </div>
  );
}
