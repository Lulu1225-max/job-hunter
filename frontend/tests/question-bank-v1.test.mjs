import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const source=readFileSync(new URL("../components/interviews/InterviewsClient.tsx",import.meta.url),"utf8");
const page=readFileSync(new URL("../app/[locale]/interviews/page.tsx",import.meta.url),"utf8");
const en=JSON.parse(readFileSync(new URL("../messages/en.json",import.meta.url),"utf8"));
const zh=JSON.parse(readFileSync(new URL("../messages/zh.json",import.meta.url),"utf8"));

test("Question Bank is an Interviews tab and does not add a navigation entry",()=>{
  assert.match(source,/activeTab===\"bank\"/);
  assert.match(source,/QuestionBankPanel/);
  assert.equal(en.interviews.bankTab,"Question Bank");
  assert.equal(zh.interviews.bankTab,"高频题库");
});

test("Question Bank supports create search category favorite edit and delete",()=>{
  assert.match(source,/\/api\/v1\/interview\/question-bank/);
  assert.match(source,/bankFavoritesOnly/);
  assert.match(source,/onBlur=.*update\(item,\{answer:/);
  assert.match(source,/\/favorite/);
  assert.match(source,/\"DELETE\"/);
  assert.match(source,/times_seen>=3/);
});

test("Interview Prep saves an answer and Actual Interview carries a stable request id",()=>{
  assert.match(source,/source:\"interview_generated\"/);
  assert.match(source,/saveToQuestion Bank|saveToBank/);
  assert.match(source,/request_id:recordRequestId/);
  assert.match(page,/\"saveToBank\"/);
});
