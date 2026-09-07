import {AnalyticsClient} from "@/components/analytics/AnalyticsClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function AnalyticsPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <AnalyticsClient copy={{title: t("nav.analytics"), subtitle: t("modules.analytics"), applications: t("dashboard.applications"), interviews: t("dashboard.interviews"), offers: t("dashboard.offers"), rejections: t("dashboard.rejections"), deadlines: t("dashboard.deadlines"), statusBreakdown: t("analytics.statusBreakdown"), loading: t("states.loading"), error: t("states.error")}} />;
}
