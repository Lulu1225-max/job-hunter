import {JobDetailClient} from "@/components/jobs/JobDetailClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function JobDetailPage({params}: {params: Promise<{locale: string; id: string}>}) {
  const {locale, id} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <JobDetailClient id={id} locale={locale} copy={{loading: t("states.loading"), error: t("states.error"), matchResume: t("jobs.matchResume"), matched: t("jobs.matched"), missing: t("jobs.missing"), none: t("jobs.noMissing"), noDescription: t("jobs.noDescription")}} />;
}
