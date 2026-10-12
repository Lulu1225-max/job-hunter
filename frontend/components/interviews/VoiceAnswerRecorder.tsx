"use client";

import {useEffect,useRef,useState} from "react";
import {Mic,Square,X} from "lucide-react";
import {apiUpload,type TranscriptionResponse} from "@/lib/api";
import {createAudioRecorderController,extensionForMimeType,MAX_AUDIO_BYTES,MAX_RECORDING_SECONDS} from "@/lib/audio-recorder.mjs";

type VoiceState="idle"|"requesting_permission"|"recording"|"uploading"|"transcribing"|"success"|"error";

export function VoiceAnswerRecorder({copy,currentText,onTranscript}:{copy:Record<string,string>;currentText:string;onTranscript:(value:string)=>void}){
 const [state,setState]=useState<VoiceState>("idle"),[elapsed,setElapsed]=useState(0),[error,setError]=useState(""),[pendingTranscript,setPendingTranscript]=useState("");
 const controllerRef=useRef<ReturnType<typeof createAudioRecorderController>|null>(null);
 const currentTextRef=useRef(currentText);currentTextRef.current=currentText;
 const onTranscriptRef=useRef(onTranscript);onTranscriptRef.current=onTranscript;
 const updateState=(next:VoiceState)=>setState(next);
 const friendlyError=(value:unknown)=>{
  const name=typeof value==="object"&&value&&"name" in value?String((value as {name?:unknown}).name):"";
  if(name==="NotAllowedError"||name==="SecurityError")return copy.voicePermissionDenied;
  if(name==="NotFoundError"||name==="DevicesNotFoundError")return copy.voiceNoMicrophone;
  if(value instanceof Error&&value.message==="recording_not_supported")return copy.voiceUnsupported;
  return copy.voiceRecordingFailed;
 };
 const upload=async({blob,durationSeconds,mimeType}:{blob:Blob;durationSeconds:number;mimeType:string})=>{
  if(!blob.size){updateState("error");setError(copy.voiceEmptyRecording);return}
  if(blob.size>MAX_AUDIO_BYTES){updateState("error");setError(copy.voiceTooLarge);return}
  updateState("uploading");setError("");
  const form=new FormData();form.append("audio",blob,`interview-answer.${extensionForMimeType(mimeType)}`);form.append("duration_seconds",String(Math.max(0.1,durationSeconds)));
  await Promise.resolve();updateState("transcribing");
  try{
   const result=await apiUpload<TranscriptionResponse>("/api/v1/interviews/transcribe",form);
   const transcript=result.transcript.trim();
   if(!transcript)throw new Error("empty_transcript");
   if(currentTextRef.current.trim())setPendingTranscript(transcript);else onTranscriptRef.current(transcript);
   updateState("success");
  }catch(_){updateState("error");setError(copy.voiceTranscriptionFailed)}
 };
 const begin=()=>{
  setError("");setPendingTranscript("");setElapsed(0);
  const controller=createAudioRecorderController({
   mediaDevices:typeof navigator!=="undefined"?navigator.mediaDevices:undefined,
   MediaRecorderClass:typeof MediaRecorder!=="undefined"?MediaRecorder:undefined,
   onState:value=>updateState(value as VoiceState),onElapsed:setElapsed,onComplete:upload,
   onError:value=>{updateState("error");setError(friendlyError(value))},maxSeconds:MAX_RECORDING_SECONDS,
  });
  controllerRef.current=controller;void controller.start();
 };
 useEffect(()=>()=>controllerRef.current?.dispose(),[]);
 const time=`${Math.floor(elapsed/60).toString().padStart(2,"0")}:${(elapsed%60).toString().padStart(2,"0")}`;
 const busy=state==="requesting_permission"||state==="uploading"||state==="transcribing";
 return <div className="mt-3 rounded-md border border-line bg-paper p-3">
  <div className="flex flex-wrap items-center gap-2">
   {state!=="recording"&&<button type="button" disabled={busy} onClick={begin} className="focus-ring inline-flex items-center gap-2 rounded-md border border-line bg-white px-3 py-2 text-sm font-medium text-ink disabled:opacity-50"><Mic className="h-4 w-4"/>{state==="requesting_permission"?copy.voiceRequestingPermission:copy.voiceAnswer}</button>}
   {state==="recording"&&<><span role="status" className="text-sm font-medium text-red-700">{copy.voiceRecording} · {time}</span><button type="button" onClick={()=>controllerRef.current?.stop()} className="inline-flex items-center gap-2 rounded-md bg-brand px-3 py-2 text-sm font-medium text-white"><Square className="h-4 w-4"/>{copy.voiceStop}</button><button type="button" onClick={()=>controllerRef.current?.cancel()} className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm"><X className="h-4 w-4"/>{copy.voiceCancel}</button></>}
   {state==="uploading"&&<span role="status" className="text-sm text-muted">{copy.voiceUploading}</span>}
   {state==="transcribing"&&<span role="status" className="text-sm text-muted">{copy.voiceTranscribing}</span>}
  </div>
  <p className="mt-2 text-xs text-muted">{copy.voiceHelp}</p>
  {error&&<p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
  {pendingTranscript&&<div className="mt-3 rounded-md border border-line bg-white p-3"><p className="text-sm text-ink">{copy.voiceExistingText}</p><p className="mt-2 line-clamp-3 text-sm text-muted">{pendingTranscript}</p><div className="mt-3 flex gap-2"><button type="button" onClick={()=>{onTranscriptRef.current(pendingTranscript);setPendingTranscript("");updateState("success")}} className="rounded-md border px-3 py-1.5 text-sm">{copy.voiceReplace}</button><button type="button" onClick={()=>{onTranscriptRef.current(`${currentTextRef.current.trim()}\n\n${pendingTranscript}`);setPendingTranscript("");updateState("success")}} className="rounded-md border px-3 py-1.5 text-sm">{copy.voiceAppend}</button></div></div>}
 </div>
}
