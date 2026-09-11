"use client";

import {useEffect,useState} from "react";
import {apiGet,apiSend,type Experience} from "@/lib/api";
const TYPES=["internship","project","coursework","leadership","volunteer","competition","other"];

export function ExperienceDetailClient({id,copy}:{id:string;copy:Record<string,string>}){
  const [item,setItem]=useState<Experience|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState<string|null>(null);const [saved,setSaved]=useState(false);
  useEffect(()=>{apiGet<Experience>(`/api/v1/experiences/${id}`).then(setItem).catch(e=>setError(e.message)).finally(()=>setLoading(false))},[id]);
  if(loading)return <State text={copy.loading}/>;if(error||!item)return <State text={copy.error}/>;
  const change=(key:string,value:unknown)=>{setSaved(false);setItem({...item,[key]:value})};
  async function save(){try{setItem(await apiSend<Experience>(`/api/v1/experiences/${id}`,"PATCH",item));setSaved(true)}catch(e){setError((e as Error).message)}}
  return <div className="space-y-6"><div className="grid gap-3 md:grid-cols-2"><Field label={copy.experienceTitle} value={item.title} onChange={v=>change("title",v)}/><label className="text-sm font-medium">{copy.type}<select value={item.type} onChange={e=>change("type",e.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3">{TYPES.map(t=><option key={t} value={t}>{copy[`type_${t}`]}</option>)}</select></label></div>
    <section className="grid gap-4 md:grid-cols-2">{["description","situation","task","action","result","reflection"].map(key=><label key={key} className="rounded-lg border border-line bg-white p-5 text-sm font-medium shadow-card">{copy[key]}<textarea value={String(item[key as keyof Experience]||"")} onChange={e=>change(key,e.target.value)} className="mt-2 min-h-28 w-full rounded-md border border-line p-3 text-sm font-normal"/></label>)}</section>
    <section className="grid gap-4 rounded-lg border border-line bg-white p-5 shadow-card md:grid-cols-2"><Field label={copy.skills} value={(item.skills||[]).join(", ")} onChange={v=>change("skills",v.split(",").map(x=>x.trim()).filter(Boolean))}/><Field label={copy.technologies} value={(item.technologies||[]).join(", ")} onChange={v=>change("technologies",v.split(",").map(x=>x.trim()).filter(Boolean))}/></section>
    {error&&<p className="text-sm text-red-700">{error}</p>}<button onClick={save} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">{copy.save}</button>{saved&&<span className="ml-3 text-sm text-emerald-700">{copy.saved}</span>}
  </div>
}
function Field({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}){return <label className="text-sm font-medium">{label}<input value={value} onChange={e=>onChange(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3"/></label>}
function State({text}:{text:string}){return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>}
