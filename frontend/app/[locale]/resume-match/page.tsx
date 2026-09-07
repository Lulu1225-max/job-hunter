import {ResumeMatchClient} from "@/components/resume-match/ResumeMatchClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ResumeMatchPage({params, searchParams}: {params: Promise<{locale: string}>; searchParams: Promise<{job?: string; resume?: string}>}) {
  const {locale} = await params;
  const query = await searchParams;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ResumeMatchClient initialJobId={query.job} initialResumeId={query.resume} copy={{title: t("resumeMatch.title"), subtitle: t("resumeMatch.subtitle"), run: t("resumeMatch.run"), overall: t("resumeMatch.overall"), keyword: t("resumeMatch.keyword"), semantic: t("resumeMatch.semantic"), experience: t("resumeMatch.experience"), matched: t("resumeMatch.matched"), missing: t("resumeMatch.missing"), evidence: t("resumeMatch.evidence"), improvements: t("resumeMatch.improvements")}} />;
}
