"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {apiGet, type Application, type DashboardOverview} from "@/lib/api";
import {ApplicationCard} from "@/components/applications/ApplicationCard";

export function DashboardClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([apiGet<DashboardOverview>("/api/v1/analytics/overview"), apiGet<Application[]>("/api/v1/applications?limit=5&sort=updated_at_desc")])
      .then(([overviewData, applicationData]) => {
        setOverview(overviewData);
        setApplications(applicationData);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <StateCard text={copy.loading} />;
  if (error) return <StateCard text={copy.error} />;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </section>
      <section className="grid gap-4 md:grid-cols-5">
        {[
          ["applications", overview?.applications_count ?? 0],
          ["interviews", overview?.interviews_count ?? 0],
          ["offers", overview?.offers_count ?? 0],
          ["rejections", overview?.rejections_count ?? 0],
          ["deadlines", overview?.upcoming_deadlines ?? 0]
        ].map(([key, value]) => (
          <Link key={key} href={metricHref(String(key), locale)} className="rounded-lg border border-line bg-white p-5 shadow-card transition hover:border-brand hover:shadow-md">
            <div className="text-sm text-muted">{copy[String(key)]}</div>
            <div className="mt-2 text-3xl font-semibold text-ink">{value}</div>
          </Link>
        ))}
      </section>
      {applications.length === 0 ? (
        <StateCard text={copy.noApplications} />
      ) : (
        <section className="grid gap-4 md:grid-cols-2">
          {applications.map((application) => (
            <ApplicationCard key={application.id} application={application} locale={locale} />
          ))}
        </section>
      )}
    </div>
  );
}

function metricHref(key: string, locale: string) {
  if (key === "offers") return `/${locale}/applications?status=offer`;
  if (key === "rejections") return `/${locale}/applications?status=rejected`;
  if (key === "interviews") return `/${locale}/applications?status=interview`;
  return `/${locale}/applications`;
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
