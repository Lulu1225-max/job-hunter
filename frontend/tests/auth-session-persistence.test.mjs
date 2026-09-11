import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const auth = readFileSync(new URL("../lib/auth.ts", import.meta.url), "utf8");
const gate = readFileSync(new URL("../components/auth/AuthGate.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("AuthGate restores a persisted session before deciding whether to redirect", () => {
  assert.match(gate, /useState<"loading" \| "authenticated" \| "unauthenticated">\("loading"\)/);
  assert.match(gate, /const session = await restoreSession\(\)/);
  assert.match(gate, /if \(session\)[\s\S]*setStatus\("authenticated"\)[\s\S]*setStatus\("unauthenticated"\)[\s\S]*router\.replace/);
  assert.match(gate, /status !== "authenticated"/);
});

test("sessions persist across refreshes and tabs and refresh before access-token expiry", () => {
  assert.match(auth, /localStorage\.setItem\(SESSION_KEY/);
  assert.match(auth, /window\.addEventListener\("storage", onStorage\)/);
  assert.match(auth, /grant_type=refresh_token/);
  assert.match(auth, /JSON\.stringify\(\{refresh_token: current\.refresh_token\}\)/);
  assert.match(auth, /startAutoRefresh/);
  assert.match(auth, /REFRESH_MARGIN_SECONDS/);
});

test("an expired API token is refreshed and the request is retried once", () => {
  assert.match(api, /const response = await send\(await getValidAccessToken\(\)\)/);
  assert.match(api, /if \(response\.status !== 401\) return response/);
  assert.match(api, /await getValidAccessToken\(true\)/);
  assert.match(api, /const retried = await send\(refreshedToken\)/);
});

test("an invalid refresh clears the session while transient network errors remain retryable", () => {
  assert.match(auth, /if \(!response\.ok\) \{\s*clearSession\(\);\s*return null/);
  assert.match(auth, /catch \{[\s\S]*return current/);
  assert.match(auth, /30_000/);
  assert.match(gate, /if \(!isPublic\) router\.replace\(`\/\$\{locale\}\/login`\)/);
});
