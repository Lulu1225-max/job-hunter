"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {apiGet, type Job} from "@/lib/api";

export function JobDetailClient({id, locale, copy}: {id: string; locale: string; copy: Record<string, string>}) {
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Job>(`/api/v1/jobs/${id}`).then(setJob).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <StateCard text={copy.loading} />;
  if (error || !job) return <StateCard text={copy.error} />;
  const match = job.match;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-semibold text-ink">{job.company}</h1>
          <p className="mt-2 text-muted">{job.role}</p>
        </div>
        <Link href={`/${locale}/resume-match?job=${job.id}`} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white shadow-card">{copy.matchResume}</Link>
      </div>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <div className="text-sm text-muted">{[job.location, job.job_type, job.deadline].filter(Boolean).join(" · ")}</div>
        <p className="mt-4 whitespace-pre-wrap text-sm text-muted">{job.description || copy.noDescription}</p>
      </section>
      {match && (
        <section className="rounded-lg border border-line bg-white p-5 shadow-card">
          <h2 className="text-xl font-semibold text-ink">{match.label}</h2>
          <p className="mt-2 text-sm text-muted">{match.reason}</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Info title={copy.matched} text={[...match.matched_skills, ...match.location_match].join(" · ") || copy.none} />
            <Info title={copy.missing} text={match.missing_skills.join(" · ") || copy.none} />
            <Info title="Components" text={match.components ? Object.entries(match.components).map(([k, v]) => `${k}: ${v}`).join("\n") : match.confidence} />
          </div>
        </section>
      )}
    </div>
  );
}

function Info({title, text}: {title: string; text: string}) {
  return <div className="rounded-md bg-paper p-3"><div className="font-medium text-ink">{title}</div><pre className="mt-2 whitespace-pre-wrap text-sm text-muted">{text}</pre></div>;
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
