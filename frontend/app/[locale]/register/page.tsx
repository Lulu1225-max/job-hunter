import {RegisterClient} from "@/components/auth/RegisterClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function RegisterPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <RegisterClient locale={locale} copy={{
    title: t("auth.register"),
    register: t("auth.register"),
    login: t("auth.login"),
    name: t("auth.name"),
    email: t("auth.email"),
    password: t("auth.password"),
    loading: t("auth.loading"),
    hasAccount: t("auth.hasAccount"),
    confirmEmail: t("auth.confirmEmail"),
    error: t("auth.registerError"),
  }} />;
}
