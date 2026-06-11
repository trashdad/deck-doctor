import { create } from "zustand";
import { authMe, trackerLogin, trackerLogout } from "@/lib/api";
import type { User } from "@/lib/types";

const USER_KEY = "simmander.user";

function cacheGet(): User | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

interface AuthState {
  user: User | null;
  ready: boolean;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  // The cookie/JWT is the source of truth for *whether* you're logged in; the
  // username is a cached display name (cleared if it doesn't match the session).
  refresh: async () => {
    const session = await authMe();
    if (!session) {
      localStorage.removeItem(USER_KEY);
      set({ user: null, ready: true });
      return;
    }
    const cached = cacheGet();
    if (cached && cached.id !== session.id) {
      localStorage.removeItem(USER_KEY);
    }
    const username = cached && cached.id === session.id ? cached.username : "";
    set({ user: { id: session.id, username }, ready: true });
  },
  login: async (username, password) => {
    const user = await trackerLogin(username, password);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ user });
  },
  logout: async () => {
    await trackerLogout();
    localStorage.removeItem(USER_KEY);
    set({ user: null });
  },
}));
