import {ApplicationDetailClient} from "@/components/applications/ApplicationDetailClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ApplicationDetailPage({params}: {params: Promise<{locale: string; id: string}>}) {
  const {locale, id} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return (
    <ApplicationDetailClient
      id={id}
      locale={locale}
      copy={{
        title: t("applications.detailTitle"),
        subtitle: t("applications.detailSubtitle"),
        loading: t("states.loading"),
        error: t("states.error"),
        prepareInterview: t("interviews.prepareInterview")
      }}
    />
  );
}
