import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-test-key";

const localValues = new Map();
const sessionValues = new Map();
const storage = (values) => ({
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: (key) => values.delete(key),
});
globalThis.window = Object.assign(new EventTarget(), {
  localStorage: storage(localValues),
  sessionStorage: storage(sessionValues),
});

const auth = await import(`../lib/auth.ts?password-recovery-test=${Date.now()}`);
const loginSource = readFileSync(new URL("../components/auth/LoginClient.tsx", import.meta.url), "utf8");
const forgotSource = readFileSync(new URL("../components/auth/ForgotPasswordClient.tsx", import.meta.url), "utf8");
const updatePage = readFileSync(new URL("../app/[locale]/update-password/page.tsx", import.meta.url), "utf8");

test.beforeEach(() => {
  localValues.clear();
  sessionValues.clear();
});

test("forgot password sends an OTP email without recovery redirect parameters", async () => {
  let request;
  const previousInfo = console.info;
  console.info = () => {};
  globalThis.fetch = async (url, options) => {
    request = {url: new URL(url), options};
    return new Response(null, {status: 200});
  };
  try {
    await auth.requestPasswordReset("student@example.com");
  } finally {
    console.info = previousInfo;
  }
  assert.equal(request.url.pathname, "/auth/v1/recover");
  assert.equal(request.url.searchParams.has("redirect_to"), false);
  assert.deepEqual(JSON.parse(request.options.body), {email: "student@example.com"});
});

test("valid recovery OTP creates a temporary recovery session", async () => {
  let request;
  const previousInfo = console.info;
  console.info = () => {};
  globalThis.fetch = async (url, options) => {
    request = {url: new URL(url), options};
    return new Response(JSON.stringify({access_token: "verified-recovery-token", refresh_token: "refresh-token", expires_in: 3600, token_type: "bearer", user: {id: "user-id"}}), {status: 200});
  };
  try {
    await auth.verifyPasswordRecoveryOtp("student@example.com", "123456");
  } finally {
    console.info = previousInfo;
  }
  assert.equal(request.url.pathname, "/auth/v1/verify");
  assert.deepEqual(JSON.parse(request.options.body), {email: "student@example.com", token: "123456", type: "recovery"});
  assert.equal(JSON.parse(sessionValues.get("jobpilot.supabase.recovery")).access_token, "verified-recovery-token");
});

test("expired recovery OTP is rejected and does not create a session", async () => {
  const previousError = console.error;
  console.error = () => {};
  globalThis.fetch = async () => new Response(JSON.stringify({error_code: "otp_expired", message: "Token has expired"}), {status: 403});
  try {
    await assert.rejects(
      () => auth.verifyPasswordRecoveryOtp("student@example.com", "000000"),
      (error) => error instanceof auth.RecoveryOtpError && error.errorType === "otp_expired",
    );
  } finally {
    console.error = previousError;
  }
  assert.equal(sessionValues.has("jobpilot.supabase.recovery"), false);
});

test("verified recovery session authorizes password update and is cleared", async () => {
  sessionValues.set("jobpilot.supabase.recovery", JSON.stringify({access_token: "verified-recovery-token", type: "recovery"}));
  let request;
  globalThis.fetch = async (url, options) => {
    request = {url, options};
    return new Response(JSON.stringify({id: "user-id"}), {status: 200});
  };
  await auth.updatePasswordWithRecovery("new-secure-password");
  assert.match(request.url, /\/auth\/v1\/user$/);
  assert.equal(request.options.headers.Authorization, "Bearer verified-recovery-token");
  assert.deepEqual(JSON.parse(request.options.body), {password: "new-secure-password"});
  assert.equal(sessionValues.has("jobpilot.supabase.recovery"), false);
});

test("OTP UI gates password fields until verification and redirects after success", () => {
  assert.match(loginSource, /href=\{`\/\$\{locale\}\/forgot-password`\}/);
  assert.match(forgotSource, /useState<"email" \| "otp" \| "password">\("email"\)/);
  assert.match(forgotSource, /verifyPasswordRecoveryOtp\(email\.trim\(\), code\.trim\(\)\)/);
  assert.match(forgotSource, /stage === "password"[\s\S]*copy\.newPassword/);
  assert.match(forgotSource, /if \(password !== confirmation\)[\s\S]*copy\.passwordMismatch/);
  assert.match(forgotSource, /await updatePasswordWithRecovery\(password\);[\s\S]*router\.replace\(`\/\$\{locale\}\/login`\)/);
  assert.match(updatePage, /redirect\(`\/\$\{locale\}\/forgot-password`\)/);
  assert.doesNotMatch(forgotSource, /ConfirmationURL|access_token|initializeRecoverySession/);
});
