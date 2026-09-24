"use client";

const SESSION_KEY = "jobpilot.supabase.session";
const AUTH_CHANGE_EVENT = "jobpilot-auth-change";
const REFRESH_MARGIN_SECONDS = 60;

export type AuthSession = {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  expires_in?: number;
  token_type?: string;
  user?: {id: string; email?: string; [key: string]: unknown};
  [key: string]: unknown;
};

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

let refreshInFlight: Promise<AuthSession | null> | null = null;

function requireSupabaseConfig() {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) throw new Error("Supabase browser configuration is missing.");
}

function tokenExpiresAt(accessToken: string): number | null {
  try {
    const encodedPayload = accessToken.split(".")[1];
    if (!encodedPayload) return null;
    const payload = JSON.parse(atob(encodedPayload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

function expiresAt(session: AuthSession): number | null {
  return session.expires_at ?? tokenExpiresAt(session.access_token);
}

function needsRefresh(session: AuthSession): boolean {
  const expiry = expiresAt(session);
  return expiry !== null && expiry <= Math.floor(Date.now() / 1000) + REFRESH_MARGIN_SECONDS;
}

function notifyAuthChange() {
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function normalizeAuthSession(payload: unknown, fallbackRefreshToken?: string): AuthSession | null {
  const response = asRecord(payload);
  if (!response) return null;

  // Supabase Auth REST responses are flat. Some auth clients expose the same
  // session under `session`, so accept both while producing one canonical shape.
  const candidate = asRecord(response.session) ?? response;
  const accessToken = candidate.access_token;
  if (typeof accessToken !== "string" || !accessToken) return null;

  const refreshToken = typeof candidate.refresh_token === "string" && candidate.refresh_token
    ? candidate.refresh_token
    : fallbackRefreshToken;
  const expiresIn = typeof candidate.expires_in === "number" ? candidate.expires_in : undefined;
  const expiresAtValue = typeof candidate.expires_at === "number"
    ? candidate.expires_at
    : expiresIn
      ? Math.floor(Date.now() / 1000) + expiresIn
      : undefined;
  const user = asRecord(candidate.user) ?? asRecord(response.user);

  return {
    ...candidate,
    access_token: accessToken,
    ...(refreshToken ? {refresh_token: refreshToken} : {}),
    ...(expiresIn !== undefined ? {expires_in: expiresIn} : {}),
    ...(expiresAtValue !== undefined ? {expires_at: expiresAtValue} : {}),
    ...(typeof candidate.token_type === "string" ? {token_type: candidate.token_type} : {}),
    ...(user && typeof user.id === "string" ? {user: user as AuthSession["user"]} : {}),
  };
}

export function getSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return normalizeAuthSession(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function setSession(payload: unknown, fallbackRefreshToken?: string): AuthSession {
  const session = normalizeAuthSession(payload, fallbackRefreshToken);
  if (!session) throw new Error("Authentication response did not contain a valid session.");
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  notifyAuthChange();
  return session;
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
  notifyAuthChange();
}

export function subscribeToAuthChanges(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === SESSION_KEY) callback();
  };
  window.addEventListener(AUTH_CHANGE_EVENT, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(AUTH_CHANGE_EVENT, callback);
    window.removeEventListener("storage", onStorage);
  };
}

export async function refreshSession(): Promise<AuthSession | null> {
  if (refreshInFlight) return refreshInFlight;
  const current = getSession();
  if (!current?.refresh_token) {
    clearSession();
    return null;
  }

  refreshInFlight = (async () => {
    try {
      requireSupabaseConfig();
      const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/token?grant_type=refresh_token`, {
        method: "POST",
        headers: {apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
        body: JSON.stringify({refresh_token: current.refresh_token}),
      });
      if (!response.ok) {
        clearSession();
        return null;
      }
      const refreshed = await response.json();
      const session = setSession(refreshed, current.refresh_token);
      return session;
    } catch {
      // A transient network failure does not prove that Supabase revoked the session.
      // Keep it so a later request or scheduled refresh can retry.
      return current;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function restoreSession(): Promise<AuthSession | null> {
  const session = getSession();
  if (!session) return null;
  return needsRefresh(session) ? refreshSession() : session;
}

export async function getValidAccessToken(forceRefresh = false): Promise<string | null> {
  const session = forceRefresh ? await refreshSession() : await restoreSession();
  return session?.access_token ?? null;
}

export function startAutoRefresh(): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  const schedule = (minimumDelay = 0) => {
    if (timer) clearTimeout(timer);
    const session = getSession();
    if (!session) return;
    const expiry = expiresAt(session);
    if (expiry === null) return;
    const delay = Math.max(minimumDelay, expiry * 1000 - Date.now() - REFRESH_MARGIN_SECONDS * 1000);
    timer = setTimeout(async () => {
      const previousToken = getSession()?.access_token;
      const refreshed = await refreshSession();
      if (!stopped) schedule(refreshed?.access_token === previousToken ? 30_000 : 0);
    }, Math.min(delay, 2_147_483_647));
  };
  const unsubscribe = subscribeToAuthChanges(schedule);
  schedule();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    unsubscribe();
  };
}

export async function loginWithPassword(email: string, password: string): Promise<AuthSession> {
  requireSupabaseConfig();
  const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: {apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
    body: JSON.stringify({email, password}),
  });
  if (!response.ok) throw new Error("Login failed.");
  return setSession(await response.json());
}

export function buildEmailConfirmationRedirect(locale: string, canonicalOrigin?: string, currentOrigin?: string): string {
  const configuredOrigin = canonicalOrigin?.trim();
  const fallbackOrigin = currentOrigin?.trim() || "http://localhost:3000";
  const originValue = configuredOrigin || fallbackOrigin;
  const absoluteOrigin = /^https?:\/\//i.test(originValue) ? originValue : `https://${originValue}`;
  const origin = new URL(absoluteOrigin).origin;
  const supportedLocale = locale === "zh" ? "zh" : "en";
  return new URL(`/${supportedLocale}/login`, `${origin}/`).toString();
}

export async function registerWithPassword(name: string, email: string, password: string, locale: string): Promise<AuthSession | null> {
  requireSupabaseConfig();
  const redirectTo = buildEmailConfirmationRedirect(
    locale,
    process.env.NEXT_PUBLIC_SITE_URL,
    typeof window === "undefined" ? undefined : window.location.origin,
  );
  const signupUrl = new URL(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/signup`);
  signupUrl.searchParams.set("redirect_to", redirectTo);
  const response = await fetch(signupUrl.toString(), {
    method: "POST",
    headers: {apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
    body: JSON.stringify({email, password, data: {name}}),
  });
  if (!response.ok) throw new Error("Registration failed.");
  const data = await response.json();
  const session = normalizeAuthSession(data);
  return session ? setSession(session) : null;
}

export async function loginDemo(): Promise<AuthSession> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/demo`, {method: "POST"});
  if (!response.ok) throw new Error("Demo login failed.");
  return setSession(await response.json());
}

export async function logout() {
  const token = getSession()?.access_token;
  if (token && SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY) {
    await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/logout`, {
      method: "POST",
      headers: {apikey: SUPABASE_PUBLISHABLE_KEY, Authorization: `Bearer ${token}`},
    }).catch(() => undefined);
  }
  clearSession();
}
