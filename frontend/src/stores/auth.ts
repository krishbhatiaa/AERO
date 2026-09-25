import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "analyst" | "viewer";
  avatar?: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => boolean;
  logout: () => void;
  getUser: () => User | null;
}

const DEMO_USERS: Record<string, { password: string; user: User }> = {
  "admin@ewai.gov.in": {
    password: "admin",
    user: { id: "u-001", name: "Dr. Research Lead", email: "admin@ewai.gov.in", role: "admin" },
  },
  "analyst@ewai.gov.in": {
    password: "analyst",
    user: { id: "u-002", name: "Weather Analyst", email: "analyst@ewai.gov.in", role: "analyst" },
  },
  "viewer@ewai.gov.in": {
    password: "viewer",
    user: { id: "u-003", name: "Viewer", email: "viewer@ewai.gov.in", role: "viewer" },
  },
};

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      login: (email: string, password: string): boolean => {
        const entry = DEMO_USERS[email.toLowerCase().trim()];
        if (entry && entry.password === password) {
          set({ user: entry.user, isAuthenticated: true });
          return true;
        }
        return false;
      },
      logout: () => {
        set({ user: null, isAuthenticated: false });
      },
      getUser: () => get().user,
    }),
    { name: "ewai-auth" },
  ),
);
