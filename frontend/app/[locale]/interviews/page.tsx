import {InterviewsClient} from "@/components/interviews/InterviewsClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function InterviewsPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <InterviewsClient copy={{title: t("interviews.title"), loading: t("states.loading"), round: t("interviews.round"), type: t("interviews.type"), status: t("interviews.status"), date: t("interviews.date"), topics: t("interviews.topics"), recommendedExperiences: t("interviews.recommendedExperiences"), generate: t("interviews.generate"), practice: t("interviews.practice"), analyse: t("interviews.analyse"), publicResearch: t("interviews.publicResearch"), aiGenerated: t("interviews.aiGenerated"), answer30s: t("interviews.answer30s"), answer1min: t("interviews.answer1min"), answer2min: t("interviews.answer2min")}} />;
}
