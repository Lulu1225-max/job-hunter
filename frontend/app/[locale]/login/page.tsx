import {LoginClient} from "@/components/auth/LoginClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function LoginPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <LoginClient locale={locale} copy={{
    title: t("auth.login"),
    login: t("auth.login"),
    register: t("auth.register"),
    email: t("auth.email"),
    password: t("auth.password"),
    loading: t("auth.loading"),
    demo: t("auth.demoMode"),
    noAccount: t("auth.noAccount"),
    error: t("auth.loginError"),
    demoError: t("auth.demoError"),
  }} />;
}
