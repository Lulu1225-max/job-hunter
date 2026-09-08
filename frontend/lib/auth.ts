"use client";

const SESSION_KEY = "jobpilot.supabase.session";

export type AuthSession = {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  expires_in?: number;
  token_type?: string;
  user?: {
    id: string;
    email?: string;
  };
};

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function requireSupabaseConfig() {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) {
    throw new Error("Supabase browser configuration is missing.");
  }
}

export function getSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSession;
    return session.access_token ? session : null;
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return getSession()?.access_token ?? null;
}

export function setSession(session: AuthSession) {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event("jobpilot-auth-change"));
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new Event("jobpilot-auth-change"));
}

export async function loginWithPassword(email: string, password: string): Promise<AuthSession> {
  requireSupabaseConfig();
  const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_PUBLISHABLE_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({email, password}),
  });
  if (!response.ok) {
    throw new Error("Login failed.");
  }
  const session = await response.json();
  setSession(session);
  return session;
}

export async function registerWithPassword(name: string, email: string, password: string): Promise<AuthSession | null> {
  requireSupabaseConfig();
  const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/signup`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_PUBLISHABLE_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({email, password, data: {name}}),
  });
  if (!response.ok) {
    throw new Error("Registration failed.");
  }
  const data = await response.json();
  if (data.access_token) {
    setSession(data);
    return data;
  }
  return null;
}

export async function loginDemo(): Promise<AuthSession> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/demo`, {method: "POST"});
  if (!response.ok) {
    throw new Error("Demo login failed.");
  }
  const session = await response.json();
  setSession(session);
  return session;
}

export async function logout() {
  const token = getAccessToken();
  if (token && SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY) {
    await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/logout`, {
      method: "POST",
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Authorization: `Bearer ${token}`,
      },
    }).catch(() => undefined);
  }
  clearSession();
}
