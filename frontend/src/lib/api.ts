// Thin fetch wrapper: JSON in/out, bearer token, friendly error messages.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "";
const TOKEN_KEY = "safemetric.token";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const tokenStore = {
  get: () => {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Cannot reach the SafeMetric server. Check your connection and try again.", 0);
  }
  if (res.status === 401 && token && !path.startsWith("/api/auth/login")) {
    onUnauthorized?.();
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* not json */ }
    throw new ApiError(msg, res.status);
  }
  if (raw) return (await res.blob()) as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => request<T>("POST", p, b),
  put: <T,>(p: string, b?: unknown) => request<T>("PUT", p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>("PATCH", p, b),
  del: <T,>(p: string) => request<T>("DELETE", p),
  blob: (p: string) => request<Blob>("GET", p, undefined, true),
};

export async function downloadFile(path: string, filename: string) {
  const blob = await api.blob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
