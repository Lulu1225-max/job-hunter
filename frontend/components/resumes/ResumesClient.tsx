"use client";

import Link from "next/link";
import {ChangeEvent, useEffect, useRef, useState} from "react";
import {Save, Upload} from "lucide-react";
import {
  apiGet,
  apiSend,
  apiUpload,
  type CareerProfile,
  type DetectedSkills,
  type Resume,
} from "@/lib/api";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const SKILL_CATEGORIES: (keyof DetectedSkills)[] = [
  "technical_skills",
  "product_skills",
  "soft_skills",
  "tools",
  "languages",
];

export function ResumesClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [profile, setProfile] = useState<CareerProfile>({});
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);
  const [preview, setPreview] = useState<Resume | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<DetectedSkills>(emptySkills());
  const fileInput = useRef<HTMLInputElement>(null);

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
    const data = await apiSend<CareerProfile>("/api/v1/profile", "PUT", profilePayload(profile));
    setProfile(normalizeProfile(data));
    setProfileSaved(true);
  }

  async function uploadResume(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    const allowedMimeTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ];
    if (!["pdf", "docx"].includes(extension ?? "") || (file.type && !allowedMimeTypes.includes(file.type))) {
      setError(copy.invalidType);
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(copy.tooLarge);
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiUpload<Resume>("/api/v1/resumes/upload", form);
      setPreview(uploaded);
      setSelectedSkills(uploaded.detected_skills);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.uploadFailed);
    } finally {
      setUploading(false);
    }
  }

  function toggleSkill(category: keyof DetectedSkills, skill: string) {
    const selected = selectedSkills[category];
    setSelectedSkills({
      ...selectedSkills,
      [category]: selected.includes(skill) ? selected.filter((item) => item !== skill) : [...selected, skill],
    });
  }

  async function confirmSkills() {
    if (!preview) return;
    setConfirming(true);
    setProfileError(null);
    try {
      const updated = await apiSend<CareerProfile>(
        `/api/v1/resumes/${preview.id}/confirm-skills`,
        "POST",
        {skills: selectedSkills},
      );
      setProfile(normalizeProfile(updated));
      setProfileSaved(true);
      setPreview(null);
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : copy.confirmFailed);
    } finally {
      setConfirming(false);
    }
  }

  async function setDefault(id: string) {
    await apiSend<Resume>(`/api/v1/resumes/${id}/default`, "PATCH");
    await load();
  }

  async function remove(id: string) {
    await apiSend<void>(`/api/v1/resumes/${id}`, "DELETE");
    if (preview?.id === id) setPreview(null);
    await load();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
          <p className="mt-2 text-muted">{copy.subtitle}</p>
        </div>
        <input ref={fileInput} className="hidden" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={uploadResume} />
        <button disabled={uploading} onClick={() => fileInput.current?.click()} className="inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card disabled:opacity-60">
          <Upload className="h-4 w-4" />
          {uploading ? copy.uploading : copy.upload}
        </button>
      </div>

      {error && <StateCard text={error} />}

      {preview && (
        <section className="space-y-4 rounded-lg border border-brand bg-white p-5 shadow-card">
          <div>
            <h2 className="text-xl font-semibold text-ink">{copy.detectedSkillsTitle}</h2>
            <p className="mt-1 text-sm text-muted">{copy.detectedSkillsSubtitle}</p>
          </div>
          {SKILL_CATEGORIES.map((category) => (
            <div key={category}>
              <h3 className="text-sm font-semibold text-ink">{skillCategoryLabel(category, copy)}</h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {preview.detected_skills[category].length === 0 && <span className="text-sm text-muted">{copy.noneDetected}</span>}
                {preview.detected_skills[category].map((skill) => (
                  <label key={skill} className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-line px-3 py-2 text-sm">
                    <input type="checkbox" checked={selectedSkills[category].includes(skill)} onChange={() => toggleSkill(category, skill)} />
                    {skill}
                  </label>
                ))}
              </div>
            </div>
          ))}
          <div className="flex flex-wrap gap-3">
            <button disabled={confirming} onClick={confirmSkills} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
              {confirming ? copy.confirming : copy.confirmSkills}
            </button>
            <button onClick={() => setPreview(null)} className="rounded-md border border-line px-4 py-2 text-sm">{copy.skipSkills}</button>
          </div>
        </section>
      )}

      <section className="space-y-4 rounded-lg border border-line bg-white p-5 shadow-card">
        <div>
          <h2 className="text-xl font-semibold text-ink">{copy.jobSearchInfoTitle}</h2>
          <p className="mt-1 text-sm text-muted">{copy.jobSearchInfoSubtitle}</p>
        </div>
        {profileLoading && <StateCard text={copy.loading} compact />}
        {profileError && <StateCard text={profileError} compact />}
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
                <select className="mt-2 h-10 w-full rounded-md border border-line px-3 text-sm" value={profile.ai_response_language ?? "chinese"} onChange={(event) => setProfile({...profile, ai_response_language: event.target.value})}>
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
              <button onClick={saveProfile} className="inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card">
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
        {loading && <StateCard text={copy.loading} />}
        {!loading && resumes.length === 0 && <StateCard text={copy.empty} />}
        <div className="grid gap-4 md:grid-cols-2">
          {resumes.map((resume) => (
            <article key={resume.id} className="rounded-lg border border-line bg-white p-5 shadow-card">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-ink">{resume.name}</h2>
                  <p className="mt-2 text-sm text-muted">{resume.file_type.toUpperCase()} · {copy.uploaded}: {resume.created_at?.slice(0, 10)}</p>
                </div>
                {resume.is_default && <span className="rounded-md bg-mintsoft px-3 py-1 text-sm font-medium text-emerald-700">{copy.default}</span>}
              </div>
              <p className="mt-4 text-sm text-muted">{copy.status}: {resume.extracted_text ? copy.extracted : copy.pending}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {SKILL_CATEGORIES.flatMap((category) => resume.detected_skills?.[category] ?? []).map((skill) => (
                  <span key={skill} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">{skill}</span>
                ))}
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                <Link href={`/${locale}/resumes/${resume.id}`} className="rounded-md border border-line px-3 py-2 text-sm">{copy.view}</Link>
                <Link href={`/${locale}/resume-match?resume=${resume.id}`} className="rounded-md border border-line px-3 py-2 text-sm">{copy.useForMatch}</Link>
                <button onClick={() => { setPreview(resume); setSelectedSkills(resume.detected_skills); }} className="rounded-md border border-line px-3 py-2 text-sm">{copy.reviewSkills}</button>
                <button onClick={() => setDefault(resume.id)} className="rounded-md border border-line px-3 py-2 text-sm">{copy.setDefault}</button>
                <button onClick={() => remove(resume.id)} className="rounded-md border border-line px-3 py-2 text-sm text-red-600">{copy.delete}</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function TextField({label, value, onChange}: {label: string; value: string; onChange: (value: string) => void}) {
  return <label className="block text-sm font-medium text-ink">{label}<input className="mt-2 h-10 w-full rounded-md border border-line px-3 text-sm" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function profilePayload(profile: CareerProfile) {
  return {
    ...profile,
    target_roles: profile.target_roles ?? [],
    target_locations: profile.target_locations ?? [],
    target_industries: profile.target_industries ?? [],
    preferred_job_types: profile.preferred_job_types ?? [],
    technical_skills: profile.technical_skills ?? [],
    product_skills: profile.product_skills ?? [],
    soft_skills: profile.soft_skills ?? [],
    tools: profile.tools ?? [],
    languages: profile.languages ?? [],
  };
}

function normalizeProfile(data: CareerProfile): CareerProfile {
  return {...profilePayload(data), ai_response_language: data.ai_response_language ?? "chinese"};
}

function emptySkills(): DetectedSkills {
  return {technical_skills: [], product_skills: [], soft_skills: [], tools: [], languages: []};
}

function skillCategoryLabel(category: keyof DetectedSkills, copy: Record<string, string>) {
  const labels: Record<keyof DetectedSkills, string> = {
    technical_skills: copy.technicalSkills,
    product_skills: copy.productSkills,
    soft_skills: copy.softSkills,
    tools: copy.tools,
    languages: copy.languages,
  };
  return labels[category];
}

function StateCard({text, compact = false}: {text: string; compact?: boolean}) {
  return <div className={`rounded-lg border border-line bg-white text-center text-muted shadow-card ${compact ? "p-4" : "p-8"}`}>{text}</div>;
}
