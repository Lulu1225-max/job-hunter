"use client";

import {useEffect, useState} from "react";
import {apiGet, type DashboardOverview} from "@/lib/api";

export function AnalyticsClient({copy}: {copy: Record<string, string>}) {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<DashboardOverview>("/api/v1/analytics/overview").then(setOverview).catch((err) => setError(err.message));
  }, []);

  if (error) return <StateCard text={copy.error} />;
  if (!overview) return <StateCard text={copy.loading} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="grid gap-4 md:grid-cols-5">
        {[
          [copy.applications, overview.applications_count],
          [copy.interviews, overview.interviews_count],
          [copy.offers, overview.offers_count],
          [copy.rejections, overview.rejections_count],
          [copy.deadlines, overview.upcoming_deadlines],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-line bg-white p-5 shadow-card">
            <div className="text-sm text-muted">{label}</div>
            <div className="mt-2 text-3xl font-semibold text-ink">{value}</div>
          </div>
        ))}
      </section>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.statusBreakdown}</h2>
        <div className="mt-4 space-y-3">
          {Object.entries(overview.applications_by_status).map(([status, count]) => (
            <div key={status}>
              <div className="flex justify-between text-sm"><span>{status}</span><span>{count}</span></div>
              <div className="mt-1 h-2 rounded-full bg-skysoft"><div className="h-2 rounded-full bg-brand" style={{width: `${Math.max(8, (count / Math.max(overview.applications_count, 1)) * 100)}%`}} /></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
