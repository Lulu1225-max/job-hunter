import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-test-key";

const values = new Map();
globalThis.window = Object.assign(new EventTarget(), {
  localStorage: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  },
});

const auth = await import(`../lib/auth.ts?demo-session-test=${Date.now()}`);
const loginClient = readFileSync(new URL("../components/auth/LoginClient.tsx", import.meta.url), "utf8");

const flatSession = {
  access_token: "header.payload.signature",
  refresh_token: "rotating-refresh-token",
  expires_in: 3600,
  expires_at: 4102444800,
  token_type: "bearer",
  user: {id: "00000000-0000-4000-8000-000000000001", email: "demo@example.com"},
  weak_password: null,
};

test.beforeEach(() => {
  values.clear();
});

test("successful Demo response persists the complete session and notifies authenticated subscribers", async () => {
  let requests = 0;
  let observedSession = null;
  const unsubscribe = auth.subscribeToAuthChanges(() => {
    observedSession = auth.getSession();
  });
  globalThis.fetch = async () => {
    requests += 1;
    return new Response(JSON.stringify(flatSession), {status: 200});
  };

  const returned = await auth.loginDemo();

  assert.equal(requests, 1);
  assert.equal(returned.access_token, flatSession.access_token);
  assert.equal(returned.refresh_token, flatSession.refresh_token);
  assert.equal(auth.getSession()?.refresh_token, flatSession.refresh_token);
  assert.equal(observedSession?.user?.id, flatSession.user.id);
  assert.equal(JSON.parse(values.get("jobpilot.supabase.session")).weak_password, null);
  unsubscribe();
});

test("the shared normalizer accepts flat and client-wrapped Supabase sessions", () => {
  assert.deepEqual(auth.normalizeAuthSession(flatSession), flatSession);
  assert.deepEqual(
    auth.normalizeAuthSession({session: flatSession, user: flatSession.user}),
    flatSession,
  );
});

test("a persisted Demo session survives restoration used for refresh and navigation", async () => {
  auth.setSession(flatSession);
  const restored = await auth.restoreSession();
  assert.equal(restored?.access_token, flatSession.access_token);
  assert.equal(restored?.refresh_token, flatSession.refresh_token);
});

test("normal password login uses the same session normalization and persistence path", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({session: flatSession}), {status: 200});
  const returned = await auth.loginWithPassword("person@example.com", "password");
  assert.equal(returned.user?.id, flatSession.user.id);
  assert.equal(auth.getSession()?.refresh_token, flatSession.refresh_token);
});

test("failed Demo login rejects and does not persist a session", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({detail: "unavailable"}), {status: 503});
  await assert.rejects(() => auth.loginDemo(), /Demo login failed/);
  assert.equal(auth.getSession(), null);
});

test("LoginClient clears stale errors, redirects after success, and synchronously blocks duplicate submissions", () => {
  assert.match(loginClient, /async function enterDemo\(\) \{\s*if \(submissionInFlight\.current\) return;/);
  assert.match(loginClient, /submissionInFlight\.current = true;[\s\S]*await loginDemo\(\)/);
  assert.match(loginClient, /setError\(null\);[\s\S]*await loginDemo\(\)/);
  assert.match(loginClient, /catch \{\s*setError\(copy\.demoError\);\s*return;/);
  assert.match(loginClient, /setError\(null\);\s*router\.replace\(`\/\$\{locale\}\/dashboard`\)/);
  assert.match(loginClient, /disabled=\{loading\}[\s\S]*onClick=\{enterDemo\}/);
});
