import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-test-key";

const auth = await import(`../lib/auth.ts?signup-redirect-test=${Date.now()}`);
const authSource = readFileSync(new URL("../lib/auth.ts", import.meta.url), "utf8");
const registerSource = readFileSync(new URL("../components/auth/RegisterClient.tsx", import.meta.url), "utf8");

test("production signup redirects both locales to the canonical site", () => {
  const productionOrigin = "https://job-hunter-frontend-nine.vercel.app";
  assert.equal(auth.buildEmailConfirmationRedirect("en", productionOrigin, "http://localhost:3000"), `${productionOrigin}/en/login`);
  assert.equal(auth.buildEmailConfirmationRedirect("zh", productionOrigin, "http://localhost:3000"), `${productionOrigin}/zh/login`);
});

test("local signup redirects both locales to the current local origin", () => {
  assert.equal(auth.buildEmailConfirmationRedirect("en", undefined, "http://localhost:3000"), "http://localhost:3000/en/login");
  assert.equal(auth.buildEmailConfirmationRedirect("zh", undefined, "http://localhost:3000"), "http://localhost:3000/zh/login");
});

test("signup uses the supported redirect_to query parameter and receives locale", () => {
  assert.match(authSource, /searchParams\.set\("redirect_to", redirectTo\)/);
  assert.match(registerSource, /registerWithPassword\(name, email, password, locale\)/);
  assert.doesNotMatch(authSource, /job-hunter-frontend-nine\.vercel\.app/);
});
