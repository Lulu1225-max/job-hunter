import assert from "node:assert/strict";
import test from "node:test";
import {chooseRecorderMimeType,createAudioRecorderController,MAX_RECORDING_SECONDS} from "../lib/audio-recorder.mjs";

class FakeTrack { stopped=false; stop(){this.stopped=true} }
class FakeRecorder {
  static supported=[];
  static isTypeSupported(type){return this.supported.includes(type)}
  constructor(stream,options={}){this.stream=stream;this.mimeType=options.mimeType||"audio/mp4";this.state="inactive"}
  start(){this.state="recording"}
  stop(){this.state="inactive";this.ondataavailable?.({data:new Blob([new Uint8Array([1,2,3])],{type:this.mimeType})});this.onstop?.()}
}

test("Chrome prefers Opus WebM while Safari falls back to MP4",()=>{
  FakeRecorder.supported=["audio/webm;codecs=opus","audio/webm","audio/mp4"];
  assert.equal(chooseRecorderMimeType(FakeRecorder),"audio/webm;codecs=opus");
  FakeRecorder.supported=["audio/mp4"];
  assert.equal(chooseRecorderMimeType(FakeRecorder),"audio/mp4");
});

test("permission rejection enters an error path without starting a recorder",async()=>{
  const errors=[];const states=[];
  const controller=createAudioRecorderController({
    mediaDevices:{getUserMedia:async()=>{const error=new Error("denied");error.name="NotAllowedError";throw error}},
    MediaRecorderClass:FakeRecorder,onState:value=>states.push(value),onElapsed:()=>{},onComplete:()=>{},onError:error=>errors.push(error),
  });
  await controller.start();
  assert.deepEqual(states,["requesting_permission"]);
  assert.equal(errors[0].name,"NotAllowedError");
});

test("stop produces one recording and releases the microphone",async()=>{
  FakeRecorder.supported=["audio/webm"];
  const track=new FakeTrack();const recordings=[];const states=[];
  const controller=createAudioRecorderController({
    mediaDevices:{getUserMedia:async()=>({getTracks:()=>[track]})},MediaRecorderClass:FakeRecorder,
    onState:value=>states.push(value),onElapsed:()=>{},onComplete:value=>recordings.push(value),onError:assert.fail,
  });
  await controller.start();controller.stop();
  assert.ok(states.includes("recording"));
  assert.equal(recordings.length,1);
  assert.equal(recordings[0].mimeType,"audio/webm");
  assert.equal(track.stopped,true);
});

test("the five minute limit automatically stops recording",async()=>{
  const originalNow=Date.now;let now=10_000;Date.now=()=>now;
  try{
    FakeRecorder.supported=["audio/webm"];const track=new FakeTrack();let tick;const recordings=[];
    const controller=createAudioRecorderController({
      mediaDevices:{getUserMedia:async()=>({getTracks:()=>[track]})},MediaRecorderClass:FakeRecorder,
      onState:()=>{},onElapsed:()=>{},onComplete:value=>recordings.push(value),onError:assert.fail,
      setIntervalFn:callback=>{tick=callback;return 1},clearIntervalFn:()=>{},
    });
    await controller.start();now+=MAX_RECORDING_SECONDS*1000;tick();
    assert.equal(recordings.length,1);
    assert.equal(recordings[0].durationSeconds,MAX_RECORDING_SECONDS);
    assert.equal(track.stopped,true);
  }finally{Date.now=originalNow}
});

test("cancel discards audio and releases the microphone",async()=>{
  const track=new FakeTrack();let completed=false;
  const controller=createAudioRecorderController({
    mediaDevices:{getUserMedia:async()=>({getTracks:()=>[track]})},MediaRecorderClass:FakeRecorder,
    onState:()=>{},onElapsed:()=>{},onComplete:()=>{completed=true},onError:assert.fail,
  });
  await controller.start();controller.cancel();
  assert.equal(completed,false);assert.equal(track.stopped,true);
});
