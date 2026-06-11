"use client";

import { useState } from "react";
import { useAuth } from "@/store/auth";
import { LoginModal } from "./LoginModal";

export function UserMenu() {
  const { user, logout } = useAuth();
  const [showLogin, setShowLogin] = useState(false);

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

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-400" data-testid="user-name">
        {user.username || `user #${user.id}`}
      </span>
      <button
        onClick={() => void logout()}
        data-testid="logout"
        className="rounded-lg border border-edge px-2.5 py-1.5 font-semibold text-zinc-400 transition hover:border-accent hover:text-accent"
      >
        Log out
      </button>
    </div>
  );
}
