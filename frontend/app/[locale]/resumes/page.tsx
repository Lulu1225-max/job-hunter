import {ResumesClient} from "@/components/resumes/ResumesClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ResumesPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ResumesClient locale={locale} copy={{
    title: t("resumes.title"),
    subtitle: t("resumes.subtitle"),
    upload: t("resumes.upload"),
    default: t("resumes.default"),
    uploaded: t("resumes.uploaded"),
    status: t("resumes.status"),
    extracted: t("resumes.extracted"),
    pending: t("resumes.pending"),
    view: t("resumes.view"),
    useForMatch: t("resumes.useForMatch"),
    setDefault: t("resumes.setDefault"),
    delete: t("resumes.delete"),
    loading: t("states.loading"),
    error: t("states.error"),
    empty: t("states.noResumes")
  }} />;
}
