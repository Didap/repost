// Tiny typed fetch client for the Repost backend.

const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (res.status === 401) {
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError("auth required", 401);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || body.error || msg;
    } catch { /* not json */ }
    throw new ApiError(msg, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export type User = { id: number; email: string; created_at?: number };
export type Session = { authed: boolean; user?: { id: number; email: string } };
export type IGAuthState = { state: "authed" | "pending" | "none"; username?: string; last_attempt_error?: string };
export type Target = { username: string; added_at: number; last_seen_at: number | null; pending_count: number };
export type PendingPost = {
  pk: string;
  code: string;
  target: string;
  caption: string;
  media_type: number;
  product_type: string;
  media_urls: string[];
  instagram_url: string;
};
export type HistoryEntry = {
  id: number;
  pk: string;
  code: string;
  target: string;
  action: "approved" | "rejected" | "published" | "failed";
  new_pk: string | null;
  error: string | null;
  ts: number;
};
export type EventEntry = { id: number; ts: number; level: "info" | "warn" | "error"; message: string };
export type Status = {
  ig: IGAuthState;
  target_count: number;
  pending_count: number;
  polling_interval: number;
};

export const api = {
  // session
  session: () => request<Session>("/api/session"),
  login: (email: string, password: string) =>
    request<{ ok: true; user: { id: number; email: string } }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: true }>("/api/logout", { method: "POST" }),

  // users
  users: () => request<User[]>("/api/users"),
  createUser: (email: string, password: string) =>
    request<User>("/api/users", { method: "POST", body: JSON.stringify({ email, password }) }),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),

  // ig auth
  igAuth: () => request<IGAuthState>("/api/auth/ig"),
  igLogin: (sessionid: string) =>
    request<IGAuthState>("/api/auth/ig", { method: "POST", body: JSON.stringify({ sessionid }) }),
  igClearPending: () => request<{ ok: true }>("/api/auth/ig/pending", { method: "DELETE" }),

  // targets
  targets: () => request<Target[]>("/api/targets"),
  addTarget: (username: string) =>
    request<{ username: string }>("/api/targets", { method: "POST", body: JSON.stringify({ username }) }),
  removeTarget: (username: string) =>
    request<void>(`/api/targets/${encodeURIComponent(username)}`, { method: "DELETE" }),

  // pending
  pending: () => request<PendingPost[]>("/api/pending"),
  approve: (pk: string) =>
    request<{ status: string }>(`/api/pending/${encodeURIComponent(pk)}/approve`, { method: "POST" }),
  reject: (pk: string) =>
    request<void>(`/api/pending/${encodeURIComponent(pk)}/reject`, { method: "POST" }),

  // history & events
  history: (limit = 50) => request<HistoryEntry[]>(`/api/history?limit=${limit}`),
  events: (since = 0) => request<EventEntry[]>(`/api/events?since=${since}`),

  // aggregate
  status: () => request<Status>("/api/status"),
};
