import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const source=readFileSync(new URL("../components/interviews/InterviewsClient.tsx",import.meta.url),"utf8");

test("question selection is explicit and clears dependent state",()=>{
  assert.match(source,/onClick=\{\(\)=>selectQuestion\(q\.id\)\}/);
  assert.match(source,/aria-selected=\{active\}/);
  assert.match(source,/border-brand bg-skysoft ring-2/);
  assert.match(source,/function selectQuestion\(id:string\).*setRecommendations\(\[\]\).*setExperienceId\(""\).*setAnswer\(null\)/s);
});

test("retrieval requires and displays the selected question",()=>{
  assert.match(source,/copy\.selectedQuestion/);
  assert.match(source,/selected\.question/);
  assert.match(source,/disabled=\{busy\|\|!questionId\} onClick=\{retrieve\}/);
  assert.match(source,/interview\/questions\/\$\{questionId\}\/experiences/);
  assert.match(source,/copy\.selectQuestionHint/);
});

test("answer generation still requires explicit Experience selection",()=>{
  assert.match(source,/questionType===\"behavioral\"/);
  assert.match(source,/questionType===\"behavioral\"&&!experienceId/);
  assert.match(source,/regenerate:Boolean\(answer&&answer\.experience_id===\(experienceId\|\|null\)\)/);
  assert.match(source,/setExperienceId\(""\)/);
});

test("question router hides Experience Retrieval for non behavioral paths",()=>{
  assert.match(source,/questionType===\"behavioral\"&&<>/);
  assert.match(source,/questionType!==\"behavioral\"/);
  assert.match(source,/routeHelp_/);
  assert.match(source,/questions\/\$\{questionId\}\/route/);
});
