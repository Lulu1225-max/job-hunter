"use client";

import {useEffect, useState} from "react";
import {Plus} from "lucide-react";
import {apiGet, apiSend, type Application} from "@/lib/api";
import {ApplicationCard} from "@/components/applications/ApplicationCard";

const groups = [
  ["applied", "appliedGroup"],
  ["oa", "oaGroup"],
  ["interview", "interviewGroup"],
  ["offer", "offerGroup"],
  ["rejected", "rejectedGroup"],
  ["saved", "savedGroup"],
  ["final_interview", "finalInterviewGroup"],
  ["withdrawn", "withdrawnGroup"]
] as const;

export function ApplicationsClient({locale, statusFilter, copy}: {locale: string; statusFilter?: string; copy: Record<string, string>}) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    const path = statusFilter ? `/api/v1/applications?status=${encodeURIComponent(statusFilter)}` : "/api/v1/applications";
    setLoading(true);
    apiGet<Application[]>(path)
      .then(setApplications)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [statusFilter]);

  async function createApplication() {
    if (!company.trim()) return;
    setSaving(true);setError(null);
    try {await apiSend<Application>("/api/v1/applications", "POST", {company, role:role.trim()||null, status: "saved", source: "manual"});setCompany("");setRole("");await load()} catch(err) {setError((err as Error).message)} finally {setSaving(false)}
  }

  async function changeStatus(id: string, status: string) {
    await apiSend<Application>(`/api/v1/applications/${id}/status?status=${encodeURIComponent(status)}`, "PATCH");
    await load();
  }

  const grouped = groups.map(([status, labelKey]) => ({
    status,
    label: copy[labelKey],
    applications: applications.filter((application) => application.status === status)
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="grid gap-3 rounded-lg border border-line bg-white p-5 shadow-card md:grid-cols-[1fr_1fr_auto]">
        <label className="text-sm font-medium text-ink">{copy.company}<input value={company} onChange={(event) => setCompany(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" /></label>
        <label className="text-sm font-medium text-ink">{copy.role}<input value={role} onChange={(event) => setRole(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" /></label>
        <button disabled={saving||!company.trim()} onClick={createApplication} className="focus-ring mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700 disabled:opacity-50">
          <Plus className="h-4 w-4" />
          {saving?copy.saving:copy.add}
        </button>
      </section>
      {loading && <StateCard text={copy.loading} />}
      {error && <StateCard text={copy.error} />}
      {!loading && !error && applications.length === 0 && <StateCard text={copy.empty} />}
      <section className="space-y-5">
        {grouped.map((group) => (
          group.applications.length > 0 && (
            <div key={group.status} className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-normal text-muted">
                {group.label} ({group.applications.length})
              </h2>
              <div className="grid gap-4 md:grid-cols-2">
                {group.applications.map((application) => (
                  <ApplicationCard key={application.id} application={application} locale={locale} onStatusChange={changeStatus} />
                ))}
              </div>
            </div>
          )
        ))}
      </section>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
