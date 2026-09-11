import {getDictionary, translate} from "@/lib/dictionaries";
import {DashboardClient} from "@/components/dashboard/DashboardClient";

export default async function DashboardPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <DashboardClient locale={locale} copy={{
    title: t("dashboard.title"),
    subtitle: t("dashboard.subtitle"),
    applications: t("dashboard.applications"),
    interviews: t("dashboard.interviews"),
    offers: t("dashboard.offers"),
    rejections: t("dashboard.rejections"),
    deadlines: t("dashboard.deadlines"),
    loading: t("states.loading"),
    error: t("states.error"),
    noApplications: t("states.noApplications")
    ,recentApplications:t("dashboard.recentApplications"),nextActions:t("dashboard.nextActions"),roleMissing:t("jobs.roleMissing"),action_saved:t("dashboard.actions.saved"),action_applied:t("dashboard.actions.applied"),action_oa:t("dashboard.actions.oa"),action_interview:t("dashboard.actions.interview"),action_final_interview:t("dashboard.actions.final_interview"),action_offer:t("dashboard.actions.offer"),action_rejected:t("dashboard.actions.rejected"),action_withdrawn:t("dashboard.actions.withdrawn"),action_default:t("dashboard.actions.default")
  }} />;
}
