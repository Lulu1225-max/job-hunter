import {ModulePage} from "@/components/ui/ModulePage";

export default async function SettingsPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  return <ModulePage titleKey="nav.settings" bodyKey="modules.settings" locale={locale} />;
}
