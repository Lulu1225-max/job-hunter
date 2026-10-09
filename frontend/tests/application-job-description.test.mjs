import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const form = await readFile(new URL("../components/applications/ApplicationsClient.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../components/applications/ApplicationDetailClient.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");

test("manual applications submit an optional job description snapshot", () => {
  assert.match(form, /job_description:jobDescription\.trim\(\)\|\|null/);
  assert.match(form, /<textarea value=\{jobDescription\}/);
  assert.match(api, /job_description\?: string \| null/);
});

test("application detail displays the saved job description", () => {
  assert.match(detail, /application\.job_description \|\| copy\.noJobDescription/);
  assert.match(detail, /whitespace-pre-wrap/);
});
