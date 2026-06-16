"use client";

import { useState } from "react";
import { useAuth } from "@/store/auth";

export function LoginModal({ onClose }: { onClose: () => void }) {
  const login = useAuth((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      onClose();
    } catch {
      setError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-[140] bg-black/50" onClick={onClose} />
      <div
        className="fixed left-1/2 top-1/2 z-[145] w-[340px] -translate-x-1/2 -translate-y-1/2
                   rounded-xl border border-accent/50 bg-ink/90 p-5 shadow-neon backdrop-blur-md"
        data-testid="login-modal"
      >
        <p className="arcade-bevel mb-1 text-sm">Log in</p>
        <p className="mb-4 text-xs text-zinc-500">
          Uses your simmander.app account.
        </p>
        <form onSubmit={submit} className="space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username or email"
            autoFocus
            className="w-full rounded-md border border-accent/40 bg-ink/70 px-3 py-2 text-sm outline-none focus:border-accent focus:shadow-neon"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="w-full rounded-md border border-accent/40 bg-ink/70 px-3 py-2 text-sm outline-none focus:border-accent focus:shadow-neon"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy || !username || !password}
            data-testid="login-submit"
            className="w-full rounded-lg bg-gradient-to-r from-magenta to-accent py-2 text-sm font-semibold text-[#1a0033] shadow-neon transition hover:brightness-110 disabled:opacity-50"
          >
            {busy ? "Logging in…" : "Log in"}
          </button>
        </form>
        <p className="mt-3 text-center text-[11px] text-zinc-500">
          Need an account?{" "}
          <a href="https://simmander.app" className="text-accent hover:underline">
            Register on simmander.app
          </a>
        </p>
      </div>
    </>
  );
}
