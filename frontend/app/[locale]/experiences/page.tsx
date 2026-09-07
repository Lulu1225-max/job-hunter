import {ExperiencesClient} from "@/components/experiences/ExperiencesClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ExperiencesPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ExperiencesClient locale={locale} copy={{
    title: t("experiences.title"),
    subtitle: t("experiences.subtitle"),
    experienceTitle: t("experiences.experienceTitle"),
    type: t("experiences.type"),
    description: t("experiences.description"),
    add: t("experiences.add"),
    delete: t("experiences.delete"),
    loading: t("states.loading"),
    error: t("states.error"),
    empty: t("states.noExperiences")
  }} />;
}
