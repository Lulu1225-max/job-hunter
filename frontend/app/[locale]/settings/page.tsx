import Link from "next/link";
import {getDictionary,translate} from "@/lib/dictionaries";

export default async function SettingsPage({params}: {params: Promise<{locale: string}>}) {
  const {locale}=await params;
  const dictionary=await getDictionary(locale);
  const t=(key:string)=>translate(dictionary,key);
  return <div className="space-y-6">
    <div><h1 className="text-3xl font-semibold text-ink">{t("nav.settings")}</h1><p className="mt-2 text-muted">{t("modules.settings")}</p></div>
    <section className="rounded-lg border border-line bg-white p-5 shadow-card"><h2 className="text-lg font-semibold">{t("settings.uiLanguage")}</h2><p className="mt-1 text-sm text-muted">{t("settings.uiLanguageHelp")}</p><div className="mt-4 flex gap-3"><Link href="/zh/settings" aria-current={locale==="zh"?"page":undefined} className={`rounded-md border px-4 py-2 text-sm ${locale==="zh"?"border-brand bg-skysoft font-semibold":"border-line"}`}>简体中文</Link><Link href="/en/settings" aria-current={locale==="en"?"page":undefined} className={`rounded-md border px-4 py-2 text-sm ${locale==="en"?"border-brand bg-skysoft font-semibold":"border-line"}`}>English</Link></div></section>
    <section className="rounded-lg border border-line bg-white p-5 shadow-card"><h2 className="text-lg font-semibold">{t("settings.aiLanguage")}</h2><p className="mt-1 text-sm text-muted">{t("settings.aiLanguageHelp")}</p><Link href={`/${locale}/resumes`} className="mt-4 inline-flex rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">{t("settings.manageJobInfo")}</Link></section>
  </div>;
}
