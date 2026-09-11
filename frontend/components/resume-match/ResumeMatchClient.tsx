"use client";

import {useEffect, useRef, useState} from "react";
import {apiGet, apiSend, type Job, type JobPage, type Resume} from "@/lib/api";

type MatchResult = {
  analysis_id: string;
  status: "scored" | "semantic_only";
  overall_score: number | null;
  keyword_score: number | null;
  semantic_score: number;
  experience_relevance_score: number | null;
  matched_keywords: string[];
  missing_keywords: string[];
  matched_skills: string[];
  missing_skills: string[];
  evidence: {skill: string; snippet: string}[];
  weak_areas: string[];
  explanation: string;
  suggested_resume_improvements: {type: string; text: string}[];
  cached: boolean;
};

export function ResumeMatchClient({initialJobId, initialResumeId, copy}: {initialJobId?: string; initialResumeId?: string; copy: Record<string, string>}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobId, setJobId] = useState(initialJobId ?? "");
  const [resumeId, setResumeId] = useState(initialResumeId ?? "");
  const [result, setResult] = useState<MatchResult | null>(null);
  const [error,setError]=useState<string|null>(null),[running,setRunning]=useState(false),[jobSearch,setJobSearch]=useState(""),[jobLoading,setJobLoading]=useState(true),[selectedJob,setSelectedJob]=useState<Job|null>(null);
  const searchSequence=useRef(0);

  useEffect(() => {
    apiGet<Resume[]>("/api/v1/resumes").then((resumeData) => {
      setResumes(resumeData);
      setResumeId((current) => current || resumeData.find((resume) => resume.is_default)?.id || "");
    }).catch(error=>setError(error.message));
  }, []);
  useEffect(()=>{if(!initialJobId)return;apiGet<Job>(`/api/v1/jobs/${initialJobId}`).then(job=>{setSelectedJob(job);setJobId(job.id)}).catch(error=>setError(error.message))},[initialJobId]);
  useEffect(()=>{const sequence=++searchSequence.current;setJobLoading(true);const timer=window.setTimeout(async()=>{try{const params=new URLSearchParams({page:"1",page_size:"20",sort:"recommended"});if(jobSearch.trim())params.set("q",jobSearch.trim());const data=await apiGet<JobPage>(`/api/v1/jobs?${params}`);if(sequence===searchSequence.current)setJobs(data.items)}catch(error){if(sequence===searchSequence.current)setError((error as Error).message)}finally{if(sequence===searchSequence.current)setJobLoading(false)}},300);return()=>window.clearTimeout(timer)},[jobSearch]);

  async function runMatch() {
    if (!jobId || !resumeId) return;
    try{setRunning(true);setError(null);setResult(await apiSend<MatchResult>(`/api/v1/jobs/${jobId}/match?resume_id=${resumeId}`, "POST"))}catch(error){setError((error as Error).message)}finally{setRunning(false)}
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="grid gap-3 rounded-lg border border-line bg-white p-5 shadow-card md:grid-cols-[1fr_1fr_auto]">
        <div><input role="combobox" aria-controls="job-results" aria-expanded="true" value={jobSearch} onChange={event=>setJobSearch(event.target.value)} placeholder={copy.searchJobs} className="h-10 w-full rounded-md border border-line px-3 text-sm"/><select id="job-results" size={6} value={jobId} onChange={event=>{const chosen=[selectedJob,...jobs].find(job=>job?.id===event.target.value)||null;setSelectedJob(chosen);setJobId(event.target.value)}} className="mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"><option value="">{copy.selectJob}</option>{[...(selectedJob&&!jobs.some(job=>job.id===selectedJob.id)?[selectedJob]:[]),...jobs].map(job=><option key={job.id} value={job.id}>{[job.company,job.role||copy.roleMissing,job.location,job.graduation_cohort].filter(Boolean).join(" · ")}{job.match?.status==="limited_data"?` · ${copy.limitedData}`:""}</option>)}</select>{!jobLoading&&jobs.length===0&&<p className="mt-2 text-sm text-muted">{copy.noMatchingJobs}</p>}</div>
        <select value={resumeId} onChange={(event) => setResumeId(event.target.value)} className="h-10 rounded-md border border-line px-3 text-sm">
          <option value="">{copy.selectResume}</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.name}{resume.is_default ? ` (${copy.defaultResume})` : ""}</option>)}
        </select>
        <button disabled={!jobId||!resumeId||running} onClick={runMatch} className="rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-50">{running?copy.running:copy.run}</button>
      </section>
      {!resumeId&&<p className="text-sm text-muted">{copy.resumeRequired}</p>}{error&&<p className="text-sm text-red-700">{error}</p>}
      {result && (
        <section className="space-y-4">
          <div className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-2xl font-semibold text-ink">{result.status==="semantic_only"?copy.potentialMatch:`${result.overall_score}% ${copy.overall}`}</h2>
            {result.status==="semantic_only"&&<p className="mt-2 text-sm text-muted">{copy.semantic}: {result.semantic_score}% · {copy.limitedSignals}</p>}
            <p className="mt-3 text-sm text-muted">{copy.keyword}: {result.keyword_score===null?copy.keywordUnavailable:`${result.keyword_score}%`} · {copy.semantic}: {result.semantic_score}% · {copy.experience}: {result.experience_relevance_score===null?copy.experienceUnavailable:`${result.experience_relevance_score}%`}</p>
            <p className="mt-3 text-sm text-muted">{result.explanation}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Info title={copy.matched} items={[...result.matched_keywords, ...result.matched_skills]} />
            <Info title={copy.missing} items={[...result.missing_keywords, ...result.missing_skills]} />
            <Info title={copy.weakAreas} items={result.weak_areas} />
          </div>
          <section className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-lg font-semibold text-ink">{copy.evidence}</h2>
            {result.evidence.map((item) => <p key={`${item.skill}-${item.snippet}`} className="mt-3 text-sm text-muted"><span className="font-medium text-ink">{item.skill}</span>: “{item.snippet}”</p>)}
          </section>
          <section className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-lg font-semibold text-ink">{copy.improvements}</h2>
            {result.suggested_resume_improvements.map((item) => <p key={item.text} className="mt-3 text-sm text-muted"><span className="font-medium text-ink">{item.type}</span>: {item.text}</p>)}
          </section>
        </section>
      )}
    </div>
  );
}

function Info({title, items}: {title: string; items: string[]}) {
  return <div className="rounded-lg border border-line bg-white p-5 shadow-card"><h2 className="text-lg font-semibold text-ink">{title}</h2><p className="mt-3 text-sm text-muted">{items.length ? items.join(" · ") : "暂无"}</p></div>;
}
