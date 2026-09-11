"use client";

import {useEffect, useState} from "react";
import Link from "next/link";
import {apiGet, apiSend, type Experience, type ExperienceRecommendation} from "@/lib/api";

const TYPES = ["internship","project","coursework","leadership","volunteer","competition","other"];
type Draft = Omit<Experience,"id">;
const emptyDraft: Draft = {title:"",type:"project",description:"",situation:"",task:"",action:"",result:"",reflection:"",skills:[],technologies:[]};

export function ExperiencesClient({locale,copy}:{locale:string;copy:Record<string,string>}) {
  const [experiences,setExperiences]=useState<Experience[]>([]);
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [roughNotes,setRoughNotes]=useState("");
  const [questions,setQuestions]=useState<string[]>([]);
  const [query,setQuery]=useState("");
  const [recommendations,setRecommendations]=useState<ExperienceRecommendation[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null);

  async function load(){setLoading(true);try{setExperiences(await apiGet<Experience[]>("/api/v1/experiences"));setError(null)}catch(e){setError((e as Error).message)}finally{setLoading(false)}}
  useEffect(()=>{load()},[]);

  async function save(){
    if(!draft.title.trim())return;
    setBusy(true);setError(null);
    try{await apiSend("/api/v1/experiences","POST",draft);setDraft(emptyDraft);setQuestions([]);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function organize(){
    setBusy(true);setError(null);
    try{const result=await apiSend<{proposal:Draft;follow_up_questions:string[]}>("/api/v1/experiences/organize","POST",{rough_notes:roughNotes});setDraft({...emptyDraft,...result.proposal});setQuestions(result.follow_up_questions)}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function retrieve(){
    setBusy(true);setError(null);
    try{const result=await apiSend<{recommendations:ExperienceRecommendation[]}>("/api/v1/experiences/retrieve","POST",{query,limit:3});setRecommendations(result.recommendations)}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function remove(id:string){if(!window.confirm(copy.confirmDelete))return;try{await apiSend<void>(`/api/v1/experiences/${id}`,"DELETE");await load()}catch(e){setError((e as Error).message)}}
  const typeLabel=(type:string)=>copy[`type_${type}`]||type;
  return <div className="space-y-6">
    <div><h1 className="text-3xl font-semibold text-ink">{copy.title}</h1><p className="mt-2 text-muted">{copy.subtitle}</p></div>
    <section className="rounded-lg border border-line bg-white p-5 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{copy.findTitle}</h2>
      <div className="mt-3 flex gap-3"><input value={query} onChange={e=>setQuery(e.target.value)} className="h-10 flex-1 rounded-md border border-line px-3 text-sm" placeholder={copy.findPlaceholder}/><button disabled={busy||query.trim().length<2} onClick={retrieve} className="rounded-md bg-brand px-4 text-sm font-medium text-white disabled:opacity-50">{copy.find}</button></div>
      {recommendations.length>0&&<div className="mt-4 grid gap-3 md:grid-cols-3">{recommendations.map(item=><article key={item.experience_id} className="rounded-md border border-line p-4"><div className="text-xs font-medium uppercase text-brand">{copy[`relevance_${item.relevance}`]}</div><Link href={`/${locale}/experiences/${item.experience_id}`} className="mt-1 block font-semibold text-ink">{item.title}</Link><p className="mt-1 text-xs text-muted">{typeLabel(item.type)}</p><p className="mt-2 text-sm text-muted">{item.reason}</p><p className="mt-2 text-xs text-brand">{[...item.skills,...item.technologies].slice(0,5).join(" · ")}</p></article>)}</div>}
      {!busy&&query&&recommendations.length===0&&<p className="mt-3 text-sm text-muted">{copy.noRecommendations}</p>}
    </section>
    <section className="rounded-lg border border-line bg-white p-5 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{copy.organizeTitle}</h2><p className="mt-1 text-sm text-muted">{copy.organizeHelp}</p>
      <textarea value={roughNotes} onChange={e=>setRoughNotes(e.target.value)} className="mt-3 min-h-28 w-full rounded-md border border-line p-3 text-sm" placeholder={copy.roughNotes}/>
      <button disabled={busy||roughNotes.trim().length<10} onClick={organize} className="mt-3 rounded-md border border-brand px-4 py-2 text-sm font-medium text-brand disabled:opacity-50">{copy.organize}</button>
      {questions.length>0&&<div className="mt-3"><p className="text-sm font-medium">{copy.followUps}</p><ul className="mt-1 list-disc pl-5 text-sm text-muted">{questions.map(q=><li key={q}>{q}</li>)}</ul></div>}
    </section>
    <section className="rounded-lg border border-line bg-white p-5 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{copy.previewTitle}</h2><p className="mt-1 text-sm text-muted">{copy.previewHelp}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2"><Field label={copy.experienceTitle} value={draft.title} onChange={v=>setDraft({...draft,title:v})}/><label className="text-sm font-medium">{copy.type}<select value={draft.type} onChange={e=>setDraft({...draft,type:e.target.value})} className="mt-1 h-10 w-full rounded-md border border-line px-3">{TYPES.map(type=><option key={type} value={type}>{typeLabel(type)}</option>)}</select></label>{["description","situation","task","action","result","reflection"].map(key=><Area key={key} label={copy[key]} value={String(draft[key as keyof Draft]||"")} onChange={v=>setDraft({...draft,[key]:v})}/>)}</div>
      <div className="mt-3 grid gap-3 md:grid-cols-2"><Field label={copy.skills} value={draft.skills?.join(", ")||""} onChange={v=>setDraft({...draft,skills:v.split(",").map(x=>x.trim()).filter(Boolean)})}/><Field label={copy.technologies} value={draft.technologies?.join(", ")||""} onChange={v=>setDraft({...draft,technologies:v.split(",").map(x=>x.trim()).filter(Boolean)})}/></div>
      <button disabled={busy||!draft.title.trim()} onClick={save} className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{copy.confirmSave}</button>
    </section>
    {error&&<StateCard text={error}/>} {loading&&<StateCard text={copy.loading}/>} {!loading&&experiences.length===0&&<StateCard text={copy.empty}/>}
    <section className="grid gap-4 md:grid-cols-2">{experiences.map(item=><article key={item.id} className="rounded-lg border border-line bg-white p-5 shadow-card"><Link href={`/${locale}/experiences/${item.id}`}><div className="text-sm text-muted">{typeLabel(item.type)}</div><h2 className="mt-2 text-lg font-semibold">{item.title}</h2><p className="mt-2 line-clamp-3 text-sm text-muted">{item.description}</p><p className="mt-3 text-sm text-brand">{[...(item.skills||[]),...(item.technologies||[])].slice(0,5).join(" · ")}</p></Link><button onClick={()=>remove(item.id)} className="mt-4 rounded-md border border-line px-3 py-2 text-sm text-red-600">{copy.delete}</button></article>)}</section>
  </div>;
}
function Field({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}){return <label className="text-sm font-medium">{label}<input value={value} onChange={e=>onChange(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3"/></label>}
function Area({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}){return <label className="text-sm font-medium">{label}<textarea value={value} onChange={e=>onChange(e.target.value)} className="mt-1 min-h-24 w-full rounded-md border border-line p-3"/></label>}
function StateCard({text}:{text:string}){return <div className="rounded-lg border border-line bg-white p-6 text-center text-muted shadow-card">{text}</div>}
