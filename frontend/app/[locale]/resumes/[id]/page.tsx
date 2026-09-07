import {ResumeDetailClient} from "@/components/resumes/ResumeDetailClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ResumeDetailPage({params}: {params: Promise<{locale: string; id: string}>}) {
  const {locale, id} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ResumeDetailClient id={id} copy={{loading: t("states.loading"), error: t("states.error"), default: t("resumes.default"), resume: t("nav.resumes"), extractedText: t("resumes.extractedText")}} />;
}
