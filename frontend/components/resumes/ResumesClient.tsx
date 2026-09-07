"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {Upload} from "lucide-react";
import {apiGet, apiSend, type Resume} from "@/lib/api";

export function ResumesClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    apiGet<Resume[]>("/api/v1/resumes").then(setResumes).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function setDefault(id: string) {
    await apiSend<Resume>(`/api/v1/resumes/${id}/default`, "PATCH");
    await load();
  }

  async function remove(id: string) {
    await apiSend<void>(`/api/v1/resumes/${id}`, "DELETE");
    await load();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
          <p className="mt-2 text-muted">{copy.subtitle}</p>
        </div>
        <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card">
          <Upload className="h-4 w-4" />
          {copy.upload}
        </button>
      </div>
      {loading && <StateCard text={copy.loading} />}
      {error && <StateCard text={copy.error} />}
      {!loading && !error && resumes.length === 0 && <StateCard text={copy.empty} />}
      <section className="grid gap-4 md:grid-cols-2">
        {resumes.map((resume) => (
          <article key={resume.id} className="rounded-lg border border-line bg-white p-5 shadow-card">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-ink">{resume.name}</h2>
                <p className="mt-2 text-sm text-muted">PDF · {copy.uploaded}: {resume.created_at?.slice(0, 7) ?? "Sep 2026"}</p>
              </div>
              {resume.is_default && <span className="rounded-md bg-mintsoft px-3 py-1 text-sm font-medium text-emerald-700">{copy.default}</span>}
            </div>
            <p className="mt-4 text-sm text-muted">{copy.status}: {resume.extracted_text ? copy.extracted : copy.pending}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link href={`/${locale}/resumes/${resume.id}`} className="rounded-md border border-line px-3 py-2 text-sm hover:border-brand hover:text-brand">{copy.view}</Link>
              <Link href={`/${locale}/resume-match?resume=${resume.id}`} className="rounded-md border border-line px-3 py-2 text-sm hover:border-brand hover:text-brand">{copy.useForMatch}</Link>
              <button onClick={() => setDefault(resume.id)} className="rounded-md border border-line px-3 py-2 text-sm hover:border-brand hover:text-brand">{copy.setDefault}</button>
              <button onClick={() => remove(resume.id)} className="rounded-md border border-line px-3 py-2 text-sm text-red-600 hover:border-red-300">{copy.delete}</button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
