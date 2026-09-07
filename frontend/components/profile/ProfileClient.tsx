"use client";

import {useEffect, useState} from "react";
import {apiGet, apiSend} from "@/lib/api";

type Profile = {
  display_name?: string | null;
  university?: string | null;
  degree?: string | null;
  major?: string | null;
  specialisation?: string | null;
  graduation_year?: number | null;
  target_roles?: string[];
  target_locations?: string[];
  preferred_job_types?: string[];
  technical_skills?: string[];
  product_skills?: string[];
  soft_skills?: string[];
  tools?: string[];
  languages?: string[];
  ai_response_language?: string;
};

export function ProfileClient({copy}: {copy: Record<string, string>}) {
  const [profile, setProfile] = useState<Profile>({target_roles: []});
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Profile>("/api/v1/profile")
      .then((data) => setProfile(normalizeProfile(data)))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    const payload = {
      ...profile,
      target_roles: csv(profile.target_roles),
      target_locations: csv(profile.target_locations),
      preferred_job_types: csv(profile.preferred_job_types),
      technical_skills: csv(profile.technical_skills),
      product_skills: csv(profile.product_skills),
      soft_skills: csv(profile.soft_skills),
      tools: csv(profile.tools),
      languages: csv(profile.languages),
    };
    const data = await apiSend<Profile>("/api/v1/profile", "PUT", payload);
    setProfile(normalizeProfile(data));
    setSaved(true);
  }

  if (loading) return <StateCard text={copy.loading} />;
  if (error) return <StateCard text={copy.error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 max-w-3xl text-muted">{copy.subtitle}</p>
      </div>
      <section className="space-y-4 rounded-lg border border-line bg-white p-5 shadow-card">
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label={copy.displayName} value={profile.display_name ?? ""} onChange={(value) => setProfile({...profile, display_name: value})} />
          <TextField label={copy.university} value={profile.university ?? ""} onChange={(value) => setProfile({...profile, university: value})} />
          <TextField label={copy.degree} value={profile.degree ?? ""} onChange={(value) => setProfile({...profile, degree: value})} />
          <TextField label={copy.major} value={profile.major ?? ""} onChange={(value) => setProfile({...profile, major: value})} />
          <TextField label={copy.specialisation} value={profile.specialisation ?? ""} onChange={(value) => setProfile({...profile, specialisation: value})} />
          <TextField label={copy.graduationYear} value={String(profile.graduation_year ?? "")} onChange={(value) => setProfile({...profile, graduation_year: Number(value) || null})} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label={copy.targetRoles} value={profile.target_roles?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, target_roles: value.split(",")})} />
          <TextField label={copy.targetLocations} value={profile.target_locations?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, target_locations: value.split(",")})} />
          <TextField label={copy.preferredJobTypes} value={profile.preferred_job_types?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, preferred_job_types: value.split(",")})} />
          <TextField label={copy.technicalSkills} value={profile.technical_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, technical_skills: value.split(",")})} />
          <TextField label={copy.productSkills} value={profile.product_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, product_skills: value.split(",")})} />
          <TextField label={copy.softSkills} value={profile.soft_skills?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, soft_skills: value.split(",")})} />
          <TextField label={copy.tools} value={profile.tools?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, tools: value.split(",")})} />
          <TextField label={copy.languages} value={profile.languages?.join(", ") ?? ""} onChange={(value) => setProfile({...profile, languages: value.split(",")})} />
          <label className="block text-sm font-medium text-ink">
            {copy.aiResponseLanguage}
            <select className="mt-2 h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" value={profile.ai_response_language ?? "chinese"} onChange={(event) => setProfile({...profile, ai_response_language: event.target.value})}>
              <option value="chinese">{copy.aiChinese}</option>
              <option value="english">{copy.aiEnglish}</option>
              <option value="bilingual">{copy.aiBilingual}</option>
            </select>
          </label>
        </div>
        <button onClick={save} className="h-10 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700">{copy.save}</button>
        {saved && <span className="ml-3 text-sm text-emerald-700">{copy.saved}</span>}
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

function csv(values?: string[]) {
  return String(values?.join(",") ?? "").split(",").map((item) => item.trim()).filter(Boolean);
}

function normalizeProfile(data: Profile): Profile {
  return {
    ...data,
    target_roles: data.target_roles ?? [],
    target_locations: data.target_locations ?? [],
    preferred_job_types: data.preferred_job_types ?? [],
    technical_skills: data.technical_skills ?? [],
    product_skills: data.product_skills ?? [],
    soft_skills: data.soft_skills ?? [],
    tools: data.tools ?? [],
    languages: data.languages ?? [],
    ai_response_language: data.ai_response_language ?? "chinese",
  };
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
