import {getDictionary, translate} from "@/lib/dictionaries";
import {ProfileClient} from "@/components/profile/ProfileClient";

export default async function ProfilePage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ProfileClient copy={{
    title: t("nav.profile"),
    subtitle: t("modules.profile"),
    displayName: t("profile.displayName"),
    university: t("profile.university"),
    degree: t("profile.degree"),
    major: t("profile.major"),
    specialisation: t("profile.specialisation"),
    graduationYear: t("profile.graduationYear"),
    targetRoles: t("profile.targetRoles"),
    targetLocations: t("profile.targetLocations"),
    preferredJobTypes: t("profile.preferredJobTypes"),
    technicalSkills: t("profile.technicalSkills"),
    productSkills: t("profile.productSkills"),
    softSkills: t("profile.softSkills"),
    tools: t("profile.tools"),
    languages: t("profile.languages"),
    aiResponseLanguage: t("profile.aiResponseLanguage"),
    aiChinese: t("profile.aiChinese"),
    aiEnglish: t("profile.aiEnglish"),
    aiBilingual: t("profile.aiBilingual"),
    save: t("profile.save"),
    saved: t("profile.saved"),
    loading: t("states.loading"),
    error: t("states.error")
  }} />;
}
