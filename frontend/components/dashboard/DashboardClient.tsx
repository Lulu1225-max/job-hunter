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
    <div className="page-stack">
      <section>
        <h1 className="page-heading">{copy.title}</h1>
        <p className="page-subtitle">{copy.subtitle}</p>
      </section>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {[
          ["applications", overview?.applications_count ?? 0],
          ["interviews", overview?.interviews_count ?? 0],
          ["offers", overview?.offers_count ?? 0],
          ["rejections", overview?.rejections_count ?? 0],
          ["deadlines", overview?.upcoming_deadlines ?? 0]
        ].map(([key, value]) => (
          <Link key={key} href={metricHref(String(key), locale)} className="surface-card group p-6 hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md">
            <div className="text-sm font-medium text-muted">{copy[String(key)]}</div>
            <div className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-ink group-hover:text-brand">{value}</div>
          </Link>
        ))}
      </section>
      {applications.length === 0 ? (
        <StateCard text={copy.noApplications} />
      ) : (
        <section><h2 className="section-heading mb-4">{copy.recentApplications}</h2><div className="grid gap-5 md:grid-cols-2">
          {applications.map((application) => (
            <ApplicationCard key={application.id} application={application} locale={locale} />
          ))}
        </div></section>
      )}
      {applications.length>0&&<section><h2 className="section-heading mb-4">{copy.nextActions}</h2><div className="space-y-3">{applications.slice(0,3).map(application=><Link key={application.id} href={`/${locale}/applications/${application.id}`} className="surface-card flex items-center justify-between gap-4 p-5 text-sm hover:border-brand/40 hover:shadow-md"><span className="font-medium">{application.company} · {application.role||copy.roleMissing}</span><span className="font-semibold text-brand">{copy[`action_${application.status}`]||copy.action_default}</span></Link>)}</div></section>}
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
  return <div className="surface-card p-10 text-center text-muted">{text}</div>;
}
