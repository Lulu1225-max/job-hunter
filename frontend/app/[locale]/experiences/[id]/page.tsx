import {ExperienceDetailClient} from "@/components/experiences/ExperienceDetailClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ExperienceDetailPage({params}: {params: Promise<{locale: string; id: string}>}) {
  const {locale, id} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ExperienceDetailClient id={id} copy={{loading: t("states.loading"), error: t("states.error"), save: t("experiences.save")}} />;
}
