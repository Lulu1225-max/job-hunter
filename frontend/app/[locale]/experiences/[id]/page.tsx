import {ExperienceDetailClient} from "@/components/experiences/ExperienceDetailClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ExperienceDetailPage({params}: {params: Promise<{locale: string; id: string}>}) {
  const {locale, id} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ExperienceDetailClient id={id} copy={{loading:t("states.loading"),error:t("states.error"),save:t("experiences.save"),saved:t("profile.saved"),experienceTitle:t("experiences.experienceTitle"),type:t("experiences.type"),description:t("experiences.description"),situation:t("experiences.situation"),task:t("experiences.task"),action:t("experiences.action"),result:t("experiences.result"),reflection:t("experiences.reflection"),skills:t("experiences.skills"),technologies:t("experiences.technologies"),type_internship:t("experiences.type_internship"),type_project:t("experiences.type_project"),type_coursework:t("experiences.type_coursework"),type_leadership:t("experiences.type_leadership"),type_volunteer:t("experiences.type_volunteer"),type_competition:t("experiences.type_competition"),type_other:t("experiences.type_other")}} />;
}
