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

test("experience answer generation requires explicit Experience selection",()=>{
  assert.match(source,/questionType===\"experience\"/);
  assert.match(source,/questionType===\"experience\"&&!experienceId/);
  assert.match(source,/regenerate:Boolean\(answer&&answer\.answer_length===answerLength&&answer\.experience_id===\(experienceId\|\|null\)\)/);
  assert.match(source,/setExperienceId\(""\)/);
});

test("question router hides Experience Retrieval for non experience paths",()=>{
  assert.match(source,/questionType===\"experience\"&&<>/);
  assert.match(source,/questionType!==\"experience\"/);
  assert.match(source,/routeHelp_/);
  assert.match(source,/questions\/\$\{questionId\}\/route/);
});

test("only the selected answer length is rendered and used",()=>{
  assert.match(source,/ANSWER_FIELD_BY_LENGTH/);
  assert.match(source,/Info title=\{copy\[`answer\$\{answerLength\}`\]\} text=\{answerForLength\(answer,answerLength\)\}/);
  assert.doesNotMatch(source,/Info title=\{copy\.answer30s\}.*Info title=\{copy\.answer1min\}.*Info title=\{copy\.answer2min\}/s);
  assert.match(source,/const text=userAnswer\|\|answerForLength\(answer,answerLength\)\|\|""/);
});

test("regenerate applies only to the currently generated length",()=>{
  assert.match(source,/answer\.answer_length===answerLength/);
  assert.match(source,/setAnswerLength\(e\.target\.value\);setAnswer\(null\);setFeedback\(null\)/);
});
