"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Z } from "@/ui/tokens";
import { Toast } from "./Toast";
import { useToasts } from "./toastStore";

/** Mount once per page. Toasts stack bottom-centre, above sheets and menus. */
export function ToastHost() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return createPortal(
    <div
      data-testid="toast-host"
      className="pointer-events-none fixed inset-x-0 bottom-4 flex flex-col items-center gap-2 px-4"
      style={{ zIndex: Z.toast }}
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto w-full max-w-[420px]">
          <Toast toast={t} onDismiss={() => dismiss(t.id)} />
        </div>
      ))}
    </div>,
    document.body,
  );
}
