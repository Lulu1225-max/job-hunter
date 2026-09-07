import {getDictionary, translate} from "@/lib/dictionaries";
import {JobsClient} from "@/components/jobs/JobsClient";

export default async function JobsPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);

  return <JobsClient locale={locale} copy={{
    title: t("jobs.title"),
    subtitle: t("jobs.subtitle"),
    import: t("jobs.import"),
    keyword: t("jobs.filters.keyword"),
    loading: t("states.loading"),
    error: t("states.error"),
    empty: t("states.noJobs"),
    deadline: t("jobs.deadline"),
    roleMissing: t("jobs.roleMissing"),
    metaMissing: t("jobs.metaMissing"),
    recommended: t("jobs.recommended"),
    allJobs: t("jobs.allJobs"),
    matched: t("jobs.matched"),
    missing: t("jobs.missing"),
    noMissing: t("jobs.noMissing"),
    sortRecommended: t("jobs.sort.recommended"),
    sortMatch: t("jobs.sort.match"),
    sortDeadline: t("jobs.sort.deadline"),
    sortNewest: t("jobs.sort.newest")
  }} />;
}
