import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const jobsClient = await readFile(new URL("../components/jobs/JobsClient.tsx", import.meta.url), "utf8");

test("Job Discovery keeps its controls and cards within one responsive content boundary", () => {
  assert.match(jobsClient, /max-w-\[1160px\]/);
  assert.match(jobsClient, /min-w-0 flex-1/);
  assert.match(jobsClient, /sm:w-24/);
});

test("the job list uses two columns only on desktop", () => {
  assert.match(jobsClient, /grid grid-cols-1 gap-4 lg:grid-cols-2/);
  assert.match(jobsClient, /lg:col-span-2/);
  assert.doesNotMatch(jobsClient, /lg:grid-cols-\[minmax\(0,2fr\)/);
});

test("each job card keeps a compact vertical information and match layout", () => {
  assert.match(jobsClient, /surface-card flex h-full flex-col p-4/);
  assert.match(jobsClient, /mt-4 flex flex-1 flex-col justify-between border-t border-line pt-4/);
  assert.match(jobsClient, /btn-primary mt-4 w-fit/);
});

test("an absent match renders the existing ready-to-match message", () => {
  assert.match(jobsClient, /if\(!match\)return <p[^>]*>\{copy\.readyToMatch\}<\/p>/);
});
