import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const source=readFileSync(new URL("../components/interviews/InterviewsClient.tsx",import.meta.url),"utf8");
const page=readFileSync(new URL("../app/[locale]/interviews/page.tsx",import.meta.url),"utf8");

test("Prepare Interview preselects the recording Application",()=>{
 assert.match(source,/useState\(initialApplicationId\|\|""\)/);
 assert.match(source,/setRecordAppId\(current=>current\|\|initialApplicationId\)/);
});

test("recording uses a visible owned Application selector and complete labels",()=>{
 assert.match(source,/copy\.applicationJob/);
 for(const key of ["date","round","type","outcome","difficulty","confidence","notes","interviewer_notes","went_well","to_improve","actualQuestions"])assert.match(source,new RegExp(`copy\\.${key}`));
 assert.match(page,/"applicationJob"/);
 assert.match(source,/applicationLabel\(a\)/);
 assert.match(source,/role\|\|copy\.roleMissing/);
});

test("successful save immediately displays the returned Interview and success feedback",()=>{
 assert.match(source,/const saved=await apiSend<Interview>\("\/api\/v1\/interviews","POST"/);
 assert.match(source,/setHistory\(current=>\[saved,/);
 assert.match(source,/setSuccess\(copy\.interviewSaved\)/);
 assert.match(source,/role="status"/);
});

test("history records are expandable and show actual Interview details",()=>{
 assert.match(source,/aria-expanded=\{open\}/);
 assert.match(source,/setSelectedHistoryId/);
 assert.match(source,/h\.actual_questions/);
});
