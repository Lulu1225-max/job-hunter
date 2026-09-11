"use client";

import {useEffect, useState} from "react";
import {apiGet, type Application} from "@/lib/api";
import {ApplicationCard} from "@/components/applications/ApplicationCard";
import Link from "next/link";

export function ApplicationDetailClient({id, locale, copy}: {id: string; locale: string; copy: Record<string, string>}) {
  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Application>(`/api/v1/applications/${id}`)
      .then(setApplication)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <StateCard text={copy.loading} />;
  if (error || !application) return <StateCard text={copy.error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <ApplicationCard application={application} locale={locale} />
      <Link href={`/${locale}/interviews?application_id=${application.id}`} className="inline-flex rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">{copy.prepareInterview}</Link>
      {application.notes && (
        <section className="rounded-lg border border-line bg-white p-5 text-sm text-muted shadow-card">
          {application.notes}
        </section>
      )}
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
