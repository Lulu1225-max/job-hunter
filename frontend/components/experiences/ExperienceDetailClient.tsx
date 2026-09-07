"use client";

import {useEffect, useState} from "react";
import {apiGet, apiSend, type Experience} from "@/lib/api";

export function ExperienceDetailClient({id, copy}: {id: string; copy: Record<string, string>}) {
  const [experience, setExperience] = useState<Experience | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Experience>(`/api/v1/experiences/${id}`).then(setExperience).catch((err) => setError(err.message)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <StateCard text={copy.loading} />;
  if (error || !experience) return <StateCard text={copy.error} />;

  async function save() {
    if (!experience) return;
    setExperience(await apiSend<Experience>(`/api/v1/experiences/${experience.id}`, "PUT", experience));
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-sm font-medium text-brand">{experience.type}</div>
        <h1 className="mt-2 text-3xl font-semibold text-ink">{experience.title}</h1>
        <textarea value={experience.description ?? ""} onChange={(event) => setExperience({...experience, description: event.target.value})} className="mt-3 min-h-20 w-full rounded-md border border-line p-3 text-sm text-muted" />
      </div>
      <section className="grid gap-4 md:grid-cols-2">
        {["situation", "task", "action", "result"].map((key) => (
          <article key={key} className="rounded-lg border border-line bg-white p-5 shadow-card">
            <h2 className="text-lg font-semibold capitalize text-ink">{key}</h2>
            <textarea
              value={String(experience[key as keyof Experience] || "")}
              onChange={(event) => setExperience({...experience, [key]: event.target.value})}
              className="mt-3 min-h-28 w-full rounded-md border border-line p-3 text-sm text-muted"
            />
          </article>
        ))}
      </section>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">Skills</h2>
        <p className="mt-3 text-sm text-brand">{experience.skills?.join(" · ")}</p>
        <p className="mt-3 text-sm text-muted">{experience.technologies?.join(" · ")}</p>
      </section>
      <button onClick={save} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white shadow-card">{copy.save}</button>
    </div>
  );
}

function StateCard({text}: {text: string}) {
  return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{text}</div>;
}
