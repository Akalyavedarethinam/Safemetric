import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: Record<string, string>) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    if (tokenStore.get()) api.post("/api/auth/logout").catch(() => undefined);
    tokenStore.clear();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) { setLoading(false); return; }
    try { setUser(await api.get<User>("/api/auth/me")); }
    catch { tokenStore.clear(); setUser(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => { tokenStore.clear(); setUser(null); });
    refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<{ access_token: string; user: User }>("/api/auth/login", { email, password });
    tokenStore.set(r.access_token);
    setUser(r.user);
  }, []);

  const register = useCallback(async (data: Record<string, string>) => {
    const r = await api.post<{ access_token: string; user: User }>("/api/auth/register", data);
    tokenStore.set(r.access_token);
    setUser(r.user);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout, refresh }), [user, loading, login, register, logout, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside provider");
  return c;
}
