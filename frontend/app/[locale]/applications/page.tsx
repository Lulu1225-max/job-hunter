import {getDictionary, translate} from "@/lib/dictionaries";
import {ApplicationsClient} from "@/components/applications/ApplicationsClient";

export default async function ApplicationsPage({params, searchParams}: {params: Promise<{locale: string}>; searchParams: Promise<{status?: string}>}) {
  const {locale} = await params;
  const {status} = await searchParams;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ApplicationsClient locale={locale} statusFilter={status} copy={{
    title: t("applications.title"),
    subtitle: t("applications.subtitle"),
    company: t("applications.company"),
    role: t("applications.role"),
    add: t("applications.add"),
    appliedGroup: t("applications.groups.applied"),
    oaGroup: t("applications.groups.oa"),
    interviewGroup: t("applications.groups.interview"),
    offerGroup: t("applications.groups.offer"),
    rejectedGroup: t("applications.groups.rejected"),
    savedGroup: t("applications.groups.saved"),
    finalInterviewGroup: t("applications.groups.final_interview"),
    withdrawnGroup: t("applications.groups.withdrawn"),
    loading: t("states.loading"),
    error: t("states.error"),
    empty: t("states.noApplications")
  }} />;
}
