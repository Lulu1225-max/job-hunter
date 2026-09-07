"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {Save, Upload} from "lucide-react";
import {apiGet, apiSend, type CareerProfile, type Resume} from "@/lib/api";

export function ResumesClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [profile, setProfile] = useState<CareerProfile>({});
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);

  async function load() {
    setLoading(true);
    apiGet<Resume[]>("/api/v1/resumes").then(setResumes).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }

  async function loadProfile() {
    setProfileLoading(true);
    apiGet<CareerProfile>("/api/v1/profile")
      .then((data) => setProfile(normalizeProfile(data)))
      .catch((err) => setProfileError(err.message))
      .finally(() => setProfileLoading(false));
  }

  useEffect(() => {
    load();
    loadProfile();
  }, []);

  async function saveProfile() {
    const data = await apiSend<CareerProfile>("/api/v1/profile", "PUT", {
      ...profile,
      target_roles: csv(profile.target_roles),
      target_locations: csv(profile.target_locations),
      target_industries: csv(profile.target_industries),
      preferred_job_types: csv(profile.preferred_job_types),
      technical_skills: csv(profile.technical_skills),
      product_skills: csv(profile.product_skills),
      soft_skills: csv(profile.soft_skills),
      tools: csv(profile.tools),
      languages: csv(profile.languages),
    });
    setProfile(normalizeProfile(data));
    setProfileSaved(true);
  }

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
      <section className="space-y-4 rounded-lg border border-line bg-white p-5 shadow-card">
        <div>
          <h2 className="text-xl font-semibold text-ink">{copy.jobSearchInfoTitle}</h2>
          <p className="mt-1 text-sm text-muted">{copy.jobSearchInfoSubtitle}</p>
        </div>
        {profileLoading && <StateCard text={copy.loading} compact />}
        {profileError && <StateCard text={copy.error} compact />}
        {!profileLoading && !profileError && (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <TextField label={copy.university} value={profile.university ?? ""} onChange={(value) => setProfile({...profile, university: value})} />
              <TextField label={copy.degree} value={profile.degree ?? ""} onChange={(value) => setProfile({...profile, degree: value})} />
              <TextField label={copy.major} value={profile.major ?? ""} onChange={(value) => setProfile({...profile, major: value})} />
              <TextField label={copy.specialisation} value={profile.specialisation ?? ""} onChange={(value) => setProfile({...profile, specialisation: value})} />
              <TextField label={copy.graduationYear} value={String(profile.graduation_year ?? "")} onChange={(value) => setProfile({...profile, graduation_year: Number(value) || null})} />
              <label className="block text-sm font-medium text-ink">
                {copy.aiResponseLanguage}
                <select className="mt-2 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" value={profile.ai_response_language ?? "chinese"} onChange={(event) => setProfile({...profile, ai_response_language: event.target.value})}>
                  <option value="chinese">{copy.aiChinese}</option>
                  <option value="english">{copy.aiEnglish}</option>
                  <option value="bilingual">{copy.aiBilingual}</option>
                </select>
              </label>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <TextField label={copy.targetRoles} value={profile.target_roles?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, target_roles: splitCsv(value)})} />
              <TextField label={copy.targetLocations} value={profile.target_locations?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, target_locations: splitCsv(value)})} />
              <TextField label={copy.preferredJobTypes} value={profile.preferred_job_types?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, preferred_job_types: splitCsv(value)})} />
              <TextField label={copy.technicalSkills} value={profile.technical_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, technical_skills: splitCsv(value)})} />
              <TextField label={copy.productSkills} value={profile.product_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, product_skills: splitCsv(value)})} />
              <TextField label={copy.softSkills} value={profile.soft_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, soft_skills: splitCsv(value)})} />
              <TextField label={copy.tools} value={profile.tools?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, tools: splitCsv(value)})} />
              <TextField label={copy.languages} value={profile.languages?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, languages: splitCsv(value)})} />
            </div>
            <div className="flex items-center gap-3">
              <button onClick={saveProfile} className="focus-ring inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700">
                <Save className="h-4 w-4" />
                {copy.saveJobSearchInfo}
              </button>
              {profileSaved && <span className="text-sm text-emerald-700">{copy.saved}</span>}
            </div>
          </>
        )}
      </section>
      <section className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold text-ink">{copy.libraryTitle}</h2>
          <p className="mt-1 text-sm text-muted">{copy.librarySubtitle}</p>
        </div>
      </section>
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

function TextField({label, value, onChange}: {label: string; value: string; onChange: (value: string) => void}) {
  return (
    <label className="block text-sm font-medium text-ink">
      {label}
      <input className="mt-2 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function csv(values?: string[]) {
  return values?.map((item) => item.trim()).filter(Boolean) ?? [];
}

function normalizeProfile(data: CareerProfile): CareerProfile {
  return {
    ...data,
    target_roles: data.target_roles ?? [],
    target_locations: data.target_locations ?? [],
    target_industries: data.target_industries ?? [],
    preferred_job_types: data.preferred_job_types ?? [],
    technical_skills: data.technical_skills ?? [],
    product_skills: data.product_skills ?? [],
    soft_skills: data.soft_skills ?? [],
    tools: data.tools ?? [],
    languages: data.languages ?? [],
    ai_response_language: data.ai_response_language ?? "chinese",
  };
}

function StateCard({text, compact = false}: {text: string; compact?: boolean}) {
  return <div className={`rounded-lg border border-line bg-white text-center text-muted shadow-card ${compact ? "p-4" : "p-8"}`}>{text}</div>;
}
