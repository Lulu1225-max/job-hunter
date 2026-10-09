"use client";

const SESSION_KEY = "jobpilot.supabase.session";
const RECOVERY_SESSION_KEY = "jobpilot.supabase.recovery";
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

export type RecoverySession = {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  type: "recovery";
};

export class RecoverySessionError extends Error {}

export class RecoveryOtpError extends Error {
  readonly status: number | null;
  readonly errorType: string;

  constructor(status: number | null, errorType: string) {
    super("Recovery OTP verification failed.");
    this.name = "RecoveryOtpError";
    this.status = status;
    this.errorType = errorType;
  }
}

export class PasswordResetRequestError extends Error {
  readonly status: number | null;
  readonly errorType: string;

  constructor(status: number | null, errorType: string) {
    super("Password recovery email failed.");
    this.name = "PasswordResetRequestError";
    this.status = status;
    this.errorType = errorType;
  }
}

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

type SupabaseAuthErrorPayload = {
  code?: unknown;
  error_code?: unknown;
  message?: unknown;
  msg?: unknown;
};

function passwordResetErrorType(status: number, payload: SupabaseAuthErrorPayload): string {
  const code = String(payload.error_code ?? payload.code ?? "").toLowerCase();
  const message = String(payload.message ?? payload.msg ?? "").toLowerCase();
  const details = `${code} ${message}`;
  if (status === 429 || details.includes("rate limit")) return "rate_limit";
  if (details.includes("redirect") && (details.includes("allow") || details.includes("invalid"))) return "invalid_redirect";
  if (details.includes("smtp") || details.includes("email") && details.includes("send")) return "email_delivery_config";
  if (details.includes("captcha")) return "captcha_required";
  if (status === 401 || status === 403) return "supabase_auth_rejection";
  if (status === 400 || status === 422) return "invalid_request";
  if (status >= 500) return "supabase_server_error";
  return "supabase_auth_rejection";
}

function logPasswordRecoveryDiagnostic(authStage: string, endpointType: string, status: number | null, errorType: string) {
  const diagnostic = {
    auth_stage: authStage,
    endpoint_type: endpointType,
    status,
    error_type: errorType,
  };
  if (errorType === "none") console.info("auth_diagnostic", diagnostic);
  else console.error("auth_diagnostic", diagnostic);
}

export async function requestPasswordReset(email: string): Promise<void> {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) {
    logPasswordRecoveryDiagnostic("forgot_password_request", "supabase_auth_recover", null, "configuration_missing");
    throw new PasswordResetRequestError(null, "configuration_missing");
  }
  const recoveryUrl = new URL(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/recover`);
  let response: Response;
  try {
    response = await fetch(recoveryUrl.toString(), {
      method: "POST",
      headers: {apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
      body: JSON.stringify({email}),
    });
  } catch (error) {
    const errorType = error instanceof DOMException && error.name === "AbortError" ? "timeout" : "network_error";
    logPasswordRecoveryDiagnostic("forgot_password_request", "supabase_auth_recover", null, errorType);
    throw new PasswordResetRequestError(null, errorType);
  }
  if (!response.ok) {
    let payload: SupabaseAuthErrorPayload = {};
    try {
      payload = await response.clone().json() as SupabaseAuthErrorPayload;
    } catch {
      // The response body is intentionally neither required nor logged.
    }
    const errorType = passwordResetErrorType(response.status, payload);
    logPasswordRecoveryDiagnostic("forgot_password_request", "supabase_auth_recover", response.status, errorType);
    throw new PasswordResetRequestError(response.status, errorType);
  }
  logPasswordRecoveryDiagnostic("forgot_password_request", "supabase_auth_recover", response.status, "none");
}

function clearRecoverySession() {
  window.sessionStorage.removeItem(RECOVERY_SESSION_KEY);
}

function storedRecoverySession(): RecoverySession | null {
  const raw = window.sessionStorage.getItem(RECOVERY_SESSION_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as RecoverySession;
    if (!session.access_token || session.type !== "recovery") throw new Error("invalid recovery session");
    if (session.expires_at && session.expires_at <= Math.floor(Date.now() / 1000)) throw new Error("expired recovery session");
    return session;
  } catch {
    clearRecoverySession();
    return null;
  }
}

function recoveryOtpErrorType(status: number, payload: SupabaseAuthErrorPayload): string {
  const details = String(payload.error_code ?? payload.code ?? payload.message ?? payload.msg ?? "").toLowerCase();
  if (details.includes("expired")) return "otp_expired";
  if (details.includes("invalid") || details.includes("token")) return "otp_invalid";
  if (status === 429) return "rate_limit";
  if (status >= 500) return "supabase_server_error";
  return "supabase_auth_rejection";
}

export async function verifyPasswordRecoveryOtp(email: string, token: string): Promise<void> {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) {
    logPasswordRecoveryDiagnostic("recovery_otp_verification", "supabase_auth_verify", null, "configuration_missing");
    throw new RecoveryOtpError(null, "configuration_missing");
  }
  let response: Response;
  try {
    response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/verify`, {
      method: "POST",
      headers: {apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
      body: JSON.stringify({email, token, type: "recovery"}),
    });
  } catch (error) {
    const errorType = error instanceof DOMException && error.name === "AbortError" ? "timeout" : "network_error";
    logPasswordRecoveryDiagnostic("recovery_otp_verification", "supabase_auth_verify", null, errorType);
    throw new RecoveryOtpError(null, errorType);
  }
  let payload: unknown = {};
  try {
    payload = await response.json();
  } catch {
    // The response body is intentionally neither required nor logged.
  }
  if (!response.ok) {
    const errorType = recoveryOtpErrorType(response.status, asRecord(payload) ?? {});
    logPasswordRecoveryDiagnostic("recovery_otp_verification", "supabase_auth_verify", response.status, errorType);
    throw new RecoveryOtpError(response.status, errorType);
  }
  const session = normalizeAuthSession(payload);
  if (!session) {
    logPasswordRecoveryDiagnostic("recovery_otp_verification", "supabase_auth_verify", response.status, "invalid_response");
    throw new RecoveryOtpError(response.status, "invalid_response");
  }
  const recovery: RecoverySession = {
    access_token: session.access_token,
    ...(session.refresh_token ? {refresh_token: session.refresh_token} : {}),
    ...(session.expires_at ? {expires_at: session.expires_at} : {}),
    type: "recovery",
  };
  window.sessionStorage.setItem(RECOVERY_SESSION_KEY, JSON.stringify(recovery));
  logPasswordRecoveryDiagnostic("recovery_otp_verification", "supabase_auth_verify", response.status, "none");
}

export async function updatePasswordWithRecovery(password: string): Promise<void> {
  requireSupabaseConfig();
  const recovery = storedRecoverySession();
  if (!recovery) throw new RecoverySessionError("Recovery session is invalid or expired.");
  const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/auth/v1/user`, {
    method: "PUT",
    headers: {
      apikey: SUPABASE_PUBLISHABLE_KEY,
      Authorization: `Bearer ${recovery.access_token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({password}),
  });
  if (response.status === 401 || response.status === 403) {
    clearRecoverySession();
    throw new RecoverySessionError("Recovery session is invalid or expired.");
  }
  if (!response.ok) throw new Error("Password update failed.");
  clearRecoverySession();
  clearSession();
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
