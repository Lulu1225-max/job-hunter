import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const shell=readFileSync(new URL("../components/layout/AppShell.tsx",import.meta.url),"utf8");
const login=readFileSync(new URL("../components/auth/LoginClient.tsx",import.meta.url),"utf8");
const importer=readFileSync(new URL("../components/jobs/JobImportClient.tsx",import.meta.url),"utf8");
const profileRoute=readFileSync(new URL("../app/[locale]/profile/page.tsx",import.meta.url),"utf8");
const analyticsRoute=readFileSync(new URL("../app/[locale]/analytics/page.tsx",import.meta.url),"utf8");

test("visible brand and final navigation match the frozen MVP",()=>{
 assert.match(shell,/Job Hunter/);
 assert.doesNotMatch(shell,/JobPilot|PlaneTakeoff/);
 assert.match(shell,/lg:hidden/);
});

test("login core fields have visible labels and browser autocomplete",()=>{
 assert.match(login,/<label[^>]*>\{copy\.email\}/);
 assert.match(login,/autoComplete="email"/);
 assert.match(login,/<label[^>]*>\{copy\.password\}/);
 assert.match(login,/autoComplete="current-password"/);
});

test("retired UI routes redirect to their current destinations",()=>{
 assert.match(profileRoute,/redirect\(`\/\$\{locale\}\/resumes`\)/);
 assert.match(analyticsRoute,/redirect\(`\/\$\{locale\}\/dashboard`\)/);
});

test("Job Import disables duplicate upload review and confirmation actions",()=>{
 assert.match(importer,/pending!==null/);
 assert.match(importer,/pending==="upload"/);
 assert.match(importer,/pending==="review"/);
 assert.match(importer,/pending==="confirm"/);
});
