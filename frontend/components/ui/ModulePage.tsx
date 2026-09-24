import {getDictionary, translate} from "@/lib/dictionaries";

export async function ModulePage({titleKey, bodyKey, locale}: {titleKey: string; bodyKey: string; locale: string}) {
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return (
    <div className="page-stack">
      <div>
        <h1 className="page-heading">{t(titleKey)}</h1>
        <p className="page-subtitle">{t(bodyKey)}</p>
      </div>
      <section className="grid gap-4 md:grid-cols-3">
        {["Discover", "Match", "Review"].map((item) => (
          <div key={item} className="surface-card p-6">
            <div className="text-sm font-medium text-muted">{item}</div>
            <div className="mt-4 h-2 rounded-full bg-skysoft">
              <div className="h-2 w-2/3 rounded-full bg-brand" />
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
