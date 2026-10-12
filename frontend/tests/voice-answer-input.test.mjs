import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const recorder=readFileSync(new URL("../components/interviews/VoiceAnswerRecorder.tsx",import.meta.url),"utf8");
const interview=readFileSync(new URL("../components/interviews/InterviewsClient.tsx",import.meta.url),"utf8");

test("Interview Answer Practice displays a voice input beside the existing textarea",()=>{
  assert.match(interview,/VoiceAnswerRecorder copy=\{copy\} currentText=\{userAnswer\} onTranscript=\{setUserAnswer\}/);
  assert.match(recorder,/copy\.voiceAnswer/);
});

test("recording exposes stop, cancel, uploading and transcribing states",()=>{
  assert.match(recorder,/state==="recording"/);
  assert.match(recorder,/controllerRef\.current\?\.stop\(\)/);
  assert.match(recorder,/controllerRef\.current\?\.cancel\(\)/);
  assert.match(recorder,/state==="uploading"/);
  assert.match(recorder,/state==="transcribing"/);
});

test("transcript is editable and is never automatically analysed",()=>{
  assert.match(recorder,/onTranscriptRef\.current\(transcript\)/);
  assert.doesNotMatch(recorder,/analyse|feedback/);
  assert.match(interview,/onClick=\{analyse\}/);
});

test("existing text requires explicit replace or append",()=>{
  assert.match(recorder,/if\(currentTextRef\.current\.trim\(\)\)setPendingTranscript\(transcript\)/);
  assert.match(recorder,/copy\.voiceReplace/);
  assert.match(recorder,/copy\.voiceAppend/);
  assert.match(recorder,/`\$\{currentTextRef\.current\.trim\(\)\}\\n\\n\$\{pendingTranscript\}`/);
});

test("transcription failure keeps the normal text answer flow available",()=>{
  assert.match(recorder,/setError\(copy\.voiceTranscriptionFailed\)/);
  assert.match(interview,/<textarea value=\{userAnswer\} onChange=\{e=>setUserAnswer\(e\.target\.value\)\}/);
});
