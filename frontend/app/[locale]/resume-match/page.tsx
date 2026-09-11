import {ResumeMatchClient} from "@/components/resume-match/ResumeMatchClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ResumeMatchPage({params, searchParams}: {params: Promise<{locale: string}>; searchParams: Promise<{job?: string; resume?: string}>}) {
  const {locale} = await params;
  const query = await searchParams;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  const keys=["title","subtitle","run","running","overall","keyword","semantic","experience","matched","missing","weakAreas","evidence","improvements","selectJob","selectResume","defaultResume","resumeRequired","roleMissing","searchJobs","noMatchingJobs","limitedData","potentialMatch","limitedSignals","keywordUnavailable","experienceUnavailable"];
  return <ResumeMatchClient initialJobId={query.job} initialResumeId={query.resume} copy={Object.fromEntries(keys.map(key=>[key,t(`resumeMatch.${key}`)]))} />;
}
