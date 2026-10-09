"use client";

import {useEffect, useState} from "react";
import {apiGet, type Application} from "@/lib/api";
import {ApplicationCard} from "@/components/applications/ApplicationCard";
import Link from "next/link";
import {CompanyResearchPanel} from "@/components/applications/CompanyResearchPanel";

export function ApplicationDetailClient({id, locale, copy}: {id: string; locale: string; copy: Record<string, string>}) {
  const [application, setApplication] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [researchRequest, setResearchRequest] = useState(0);

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
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.jobDescription}</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted">
          {application.job_description || copy.noJobDescription}
        </p>
      </section>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={() => setResearchRequest((value) => value + 1)} className="btn-primary">{copy.companyResearch}</button>
        <Link href={`/${locale}/interviews?application_id=${application.id}`} className="btn-secondary">{copy.prepareInterview}</Link>
      </div>
      <CompanyResearchPanel applicationId={application.id} requestKey={researchRequest} />
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
