"use client";

import {useEffect, useState} from "react";
import Link from "next/link";
import {Plus} from "lucide-react";
import {apiGet, apiSend, type Experience} from "@/lib/api";

export function ExperiencesClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("project");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    apiGet<Experience[]>("/api/v1/experiences")
      .then(setExperiences)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function addExperience() {
    if (!title.trim()) return;
    await apiSend<Experience>("/api/v1/experiences", "POST", {title, type, description, skills: [], technologies: []});
    setTitle("");
    setDescription("");
    await load();
  }

  async function remove(id: string) {
    await apiSend<void>(`/api/v1/experiences/${id}`, "DELETE");
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="grid gap-3 rounded-lg border border-line bg-white p-5 shadow-card md:grid-cols-[1fr_160px_auto]">
        <input value={title} onChange={(event) => setTitle(event.target.value)} className="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100" placeholder={copy.experienceTitle} />
        <select value={type} onChange={(event) => setType(event.target.value)} className="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100">
          <option value="project">project</option>
          <option value="work">work</option>
          <option value="education">education</option>
          <option value="leadership">leadership</option>
          <option value="volunteer">volunteer</option>
        </select>
        <button onClick={addExperience} className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700">
          <Plus className="h-4 w-4" />
          {copy.add}
        </button>
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} className="min-h-24 rounded-md border border-line p-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100 md:col-span-3" placeholder={copy.description} />
      </section>
      {loading && <StateCard text={copy.loading} />}
      {error && <StateCard text={copy.error} />}
      {!loading && !error && experiences.length === 0 && <StateCard text={copy.empty} />}
      <section className="grid gap-4 md:grid-cols-2">
        {experiences.map((experience) => (
          <article key={experience.id} className="rounded-lg border border-line bg-white p-5 shadow-card">
            <Link href={`/${locale}/experiences/${experience.id}`} className="block">
              <div className="text-sm text-muted">{experience.type}</div>
              <h2 className="mt-2 text-lg font-semibold text-ink">{experience.title}</h2>
              {experience.description && <p className="mt-3 text-sm text-muted">{experience.description}</p>}
              {experience.skills && <p className="mt-4 text-sm text-brand">{experience.skills.slice(0, 5).join(" · ")}</p>}
            </Link>
            <button onClick={() => remove(experience.id)} className="mt-4 rounded-md border border-line px-3 py-2 text-sm text-red-600 hover:border-red-300">{copy.delete}</button>
          </article>
        ))}
      </section>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
