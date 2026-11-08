"use client";

import type { ToastModel } from "./toastStore";

export interface ToastProps {
  toast: ToastModel;
  onDismiss: () => void;
}

export function Toast({ toast, onDismiss }: ToastProps) {
  return (
    <div role="status" data-testid="toast" className="dd-toast">
      <span className="min-w-0 flex-1">{toast.message}</span>
      {toast.action && (
        <button
          type="button"
          data-testid="toast-action"
          onClick={() => {
            toast.action?.onClick();
            onDismiss();
          }}
          className="h-9 rounded border border-accent/50 px-3 text-[13px] font-semibold text-accent hover:bg-accent/15 focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan"
        >
          {toast.action.label}
        </button>
      )}
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onDismiss}
        className="flex h-9 w-9 items-center justify-center rounded text-zinc-400 hover:bg-accent/10 hover:text-zinc-100"
      >
        ×
      </button>
    </div>
  );
}
