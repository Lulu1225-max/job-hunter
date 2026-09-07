"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";
import {Upload} from "lucide-react";
import {Badge} from "@/components/ui/Badge";
import {apiGet, type Job} from "@/lib/api";

export function JobsClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keyword, setKeyword] = useState("");
  const [sort, setSort] = useState("recommended");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (keyword.trim()) params.set("keyword", keyword.trim());
    params.set("sort", sort);
    setLoading(true);
    apiGet<Job[]>(`/api/v1/jobs${params.size ? `?${params}` : ""}`)
      .then(setJobs)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [keyword, sort]);

  const visibleJobs = useMemo(() => jobs, [jobs]);
  const recommendedJobs = visibleJobs.filter((job) => job.match?.level === "scored").slice(0, 3);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
          <p className="mt-2 text-muted">{copy.subtitle}</p>
        </div>
        <Link href={`/${locale}/jobs/import`} className="focus-ring inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700">
          <Upload className="h-4 w-4" />
          {copy.import}
        </Link>
      </div>
      <section className="rounded-lg border border-line bg-white p-4 shadow-card">
        <div className="grid gap-3 md:grid-cols-[1fr_220px]">
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            className="h-10 w-full rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100"
            placeholder={copy.keyword}
          />
          <select value={sort} onChange={(event) => setSort(event.target.value)} className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100">
            <option value="recommended">{copy.sortRecommended}</option>
            <option value="match_score">{copy.sortMatch}</option>
            <option value="deadline">{copy.sortDeadline}</option>
            <option value="newest">{copy.sortNewest}</option>
          </select>
        </div>
      </section>
      {loading && <StateCard text={copy.loading} />}
      {error && <StateCard text={copy.error} />}
      {!loading && !error && visibleJobs.length === 0 && <StateCard text={copy.empty} />}
      {!loading && !error && recommendedJobs.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-normal text-muted">{copy.recommended}</h2>
          {recommendedJobs.map((job) => <JobCard key={job.id} job={job} locale={locale} copy={copy} />)}
        </section>
      )}
      <section className="space-y-3">
        {visibleJobs.length > 0 && <h2 className="text-sm font-semibold uppercase tracking-normal text-muted">{copy.allJobs}</h2>}
        {visibleJobs.map((job) => <JobCard key={job.id} job={job} locale={locale} copy={copy} />)}
      </section>
    </div>
  );
}

function JobCard({job, locale, copy}: {job: Job; locale: string; copy: Record<string, string>}) {
  const match = job.match;
  return (
    <Link href={`/${locale}/jobs/${job.id}`} className="block rounded-lg border border-line bg-white p-5 shadow-card transition hover:border-brand hover:shadow-md">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-ink">{job.company}</h2>
          <p className="mt-1 text-muted">{job.role || copy.roleMissing}</p>
          <p className="mt-3 text-sm text-muted">
            {[job.location, job.industry, job.graduation_cohort].filter(Boolean).join(" · ") || copy.metaMissing}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 md:justify-end">
          {match && <div className={`rounded-md px-3 py-2 text-sm font-semibold ${match.level === "scored" ? "bg-mintsoft text-emerald-700" : "bg-skysoft text-brand"}`}>{match.label}</div>}
          {job.job_type && <Badge value={job.job_type}>{job.job_type}</Badge>}
          {job.deadline && <div className="rounded-md border border-amber-200 bg-ambersoft px-3 py-2 text-sm text-amber-800">{copy.deadline}: {job.deadline}</div>}
        </div>
      </div>
      {match && (
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
          <MatchList title={copy.matched} items={[...(match.matched_skills || []), ...(match.location_match || [])]} fallback={match.reason} />
          <MatchList title={copy.missing} items={match.missing_skills || []} fallback={copy.noMissing} />
          <div className="rounded-md bg-paper p-3 text-muted">{match.reason}</div>
        </div>
      )}
    </Link>
  );
}

function MatchList({title, items, fallback}: {title: string; items: string[]; fallback: string}) {
  return (
    <div className="rounded-md bg-paper p-3">
      <div className="font-medium text-ink">{title}</div>
      <div className="mt-2 text-muted">{items.length ? items.join(" · ") : fallback}</div>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
