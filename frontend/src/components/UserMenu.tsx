"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/store/auth";
import { LoginModal } from "./LoginModal";

// TODO(product): replace with the real Patreon URL once it exists.
const PATREON_URL = "https://www.patreon.com/simmander";

export function UserMenu() {
  const { user, logout } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, []);

  if (!user) {
    return (
      <>
        <button
          onClick={() => setShowLogin(true)}
          data-testid="open-login"
          className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-semibold tracking-wide text-accent transition hover:bg-accent/10"
        >
          Log in
        </button>
        {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      </>
    );
  }

  const displayName = user.is_admin ? "Admin" : user.username || `Player #${user.id}`;
  const isMythic = user.tier === "mythic";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        data-testid="user-name"
        title="Account options"
        className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/5 px-3 py-1.5
                   text-xs font-semibold text-accent transition hover:bg-accent/15"
      >
        <span>👤 {displayName}</span>
        {isMythic && (
          <span className="rounded border border-accent/60 bg-accent px-1 text-[8px] font-bold uppercase tracking-wider text-[#1a0033] shadow-glow">
            ◆ Mythic
          </span>
        )}
        <span className="text-[9px] text-accent/70">▾</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-[130]" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-[131] mt-1 w-56 overflow-hidden rounded-lg border border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md">
            <div className="border-b border-accent/30 px-3 py-2">
              <p className="text-sm font-semibold text-zinc-100">{displayName}</p>
              <p className="text-[10px] uppercase tracking-widest text-accent">
                {isMythic ? "Mythic tier" : "Free tier"}
              </p>
            </div>
            <a
              href="https://simmander.app/"
              className="block px-3 py-2 text-xs text-zinc-300 transition hover:bg-accent/10"
            >
              ⚜ Manage account on Simmander.app
            </a>
            {!isMythic && (
              <a
                href={PATREON_URL}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="user-patreon"
                className="block px-3 py-2 text-xs font-semibold text-accent transition hover:bg-accent/10"
              >
                ★ Go Mythic on Patreon
              </a>
            )}
            <button
              onClick={() => {
                setOpen(false);
                void logout();
              }}
              data-testid="logout"
              className="block w-full border-t border-accent/30 px-3 py-2 text-left text-xs text-zinc-400 transition hover:bg-accent/10 hover:text-accent"
            >
              Log out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
