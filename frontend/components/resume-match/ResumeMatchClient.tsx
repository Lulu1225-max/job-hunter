"use client";

import {useEffect, useState} from "react";
import {apiGet, apiSend, type Job, type Resume} from "@/lib/api";

type MatchResult = {
  overall_score: number;
  keyword_score: number;
  semantic_score: number;
  experience_relevance_score: number;
  matched_keywords: string[];
  missing_keywords: string[];
  matched_skills: string[];
  missing_skills: string[];
  strong_experience_evidence: {title: string; score: number; why: string}[];
  weak_areas: string[];
  suggested_resume_improvements: {type: string; text: string}[];
};

export function ResumeMatchClient({initialJobId, initialResumeId, copy}: {initialJobId?: string; initialResumeId?: string; copy: Record<string, string>}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobId, setJobId] = useState(initialJobId ?? "");
  const [resumeId, setResumeId] = useState(initialResumeId ?? "");
  const [result, setResult] = useState<MatchResult | null>(null);

  useEffect(() => {
    Promise.all([apiGet<Job[]>("/api/v1/jobs?sort=recommended"), apiGet<Resume[]>("/api/v1/resumes")]).then(([jobData, resumeData]) => {
      setJobs(jobData);
      setResumes(resumeData);
      setJobId((current) => current || jobData[0]?.id || "");
      setResumeId((current) => current || resumeData.find((resume) => resume.is_default)?.id || resumeData[0]?.id || "");
    });
  }, []);

  async function runMatch() {
    if (!jobId) return;
    const suffix = resumeId ? `?resume_id=${resumeId}` : "";
    setResult(await apiSend<MatchResult>(`/api/v1/jobs/${jobId}/match${suffix}`, "POST"));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="grid gap-3 rounded-lg border border-line bg-white p-5 shadow-card md:grid-cols-[1fr_1fr_auto]">
        <select value={jobId} onChange={(event) => setJobId(event.target.value)} className="h-10 rounded-md border border-line px-3 text-sm">
          {jobs.map((job) => <option key={job.id} value={job.id}>{job.company} - {job.role}</option>)}
        </select>
        <select value={resumeId} onChange={(event) => setResumeId(event.target.value)} className="h-10 rounded-md border border-line px-3 text-sm">
          {resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.name}{resume.is_default ? " (Default)" : ""}</option>)}
        </select>
        <button onClick={runMatch} className="rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card">{copy.run}</button>
      </section>
      {result && (
        <section className="space-y-4">
          <div className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-2xl font-semibold text-ink">{result.overall_score}% {copy.overall}</h2>
            <p className="mt-3 text-sm text-muted">{copy.keyword} {result.keyword_score} · {copy.semantic} {result.semantic_score} · {copy.experience} {result.experience_relevance_score}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Info title={copy.matched} items={[...result.matched_keywords, ...result.matched_skills]} />
            <Info title={copy.missing} items={[...result.missing_keywords, ...result.missing_skills]} />
          </div>
          <section className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-lg font-semibold text-ink">{copy.evidence}</h2>
            {result.strong_experience_evidence.map((item) => <p key={item.title} className="mt-3 text-sm text-muted"><span className="font-medium text-ink">{item.title}</span> · {item.score}% · {item.why}</p>)}
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
