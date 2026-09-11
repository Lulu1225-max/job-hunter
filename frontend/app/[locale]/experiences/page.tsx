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
    confirmDelete: t("experiences.confirmDelete"),
    loading: t("states.loading"),
    error: t("states.error"),
    empty: t("states.noExperiences")
    ,findTitle:t("experiences.findTitle"),findPlaceholder:t("experiences.findPlaceholder"),find:t("experiences.find"),noRecommendations:t("experiences.noRecommendations"),organizeTitle:t("experiences.organizeTitle"),organizeHelp:t("experiences.organizeHelp"),roughNotes:t("experiences.roughNotes"),organize:t("experiences.organize"),followUps:t("experiences.followUps"),previewTitle:t("experiences.previewTitle"),previewHelp:t("experiences.previewHelp"),confirmSave:t("experiences.confirmSave"),situation:t("experiences.situation"),task:t("experiences.task"),action:t("experiences.action"),result:t("experiences.result"),reflection:t("experiences.reflection"),skills:t("experiences.skills"),technologies:t("experiences.technologies"),relevance_high:t("experiences.relevance_high"),relevance_medium:t("experiences.relevance_medium"),relevance_lower:t("experiences.relevance_lower"),type_internship:t("experiences.type_internship"),type_project:t("experiences.type_project"),type_coursework:t("experiences.type_coursework"),type_leadership:t("experiences.type_leadership"),type_volunteer:t("experiences.type_volunteer"),type_competition:t("experiences.type_competition"),type_other:t("experiences.type_other")
  }} />;
}
