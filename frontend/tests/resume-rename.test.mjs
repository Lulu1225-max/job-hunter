import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const detail=readFileSync(new URL("../components/resumes/ResumeDetailClient.tsx",import.meta.url),"utf8");

test("resume rename matches the backend PUT route and body schema",()=>{
  assert.match(detail,/apiSend<Resume>\(`\/api\/v1\/resumes\/\$\{id\}`,"PUT",\{name:name\.trim\(\)\}\)/);
  assert.doesNotMatch(detail,/apiSend<Resume>\(`\/api\/v1\/resumes\/\$\{id\}`,"PATCH"/);
});

test("successful rename updates the visible resume without reloading",()=>{
  assert.match(detail,/setResume\(updated\);setName\(updated\.name\)/);
});

test("rename failure stays local and does not replace the loaded page",()=>{
  assert.match(detail,/const \[loadError,\s*setLoadError\]/);
  assert.match(detail,/const \[renameError,\s*setRenameError\]/);
  assert.match(detail,/renameError&&<p role="alert"/);
  assert.doesNotMatch(detail,/if \(renameError \|\| !resume\)/);
});
