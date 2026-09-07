"use client";

import {useEffect, useState} from "react";
import {apiGet, type Resume} from "@/lib/api";

export function ResumeDetailClient({id, copy}: {id: string; copy: Record<string, string>}) {
  const [resume, setResume] = useState<Resume | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Resume>(`/api/v1/resumes/${id}`).then(setResume).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <StateCard text={copy.loading} />;
  if (error || !resume) return <StateCard text={copy.error} />;
  const content = resume.structured_content ?? {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{resume.name}</h1>
        <p className="mt-2 text-muted">{resume.is_default ? copy.default : copy.resume}</p>
      </div>
      <section className="grid gap-4 md:grid-cols-2">
        {Object.entries(content).map(([key, value]) => (
          <article key={key} className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-lg font-semibold capitalize text-ink">{key.replaceAll("_", " ")}</h2>
            <pre className="mt-3 whitespace-pre-wrap text-sm text-muted">{formatValue(value)}</pre>
          </article>
        ))}
      </section>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.extractedText}</h2>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-sm text-muted">{resume.extracted_text}</pre>
      </section>
    </div>
  );
}

function formatValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => typeof item === "object" ? Object.values(item as Record<string, unknown>).join(" · ") : String(item)).join("\n");
  }
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
