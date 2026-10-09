import {ForgotPasswordClient} from "@/components/auth/ForgotPasswordClient";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function ForgotPasswordPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return <ForgotPasswordClient locale={locale} copy={{
    title: t("auth.forgotPasswordTitle"), description: t("auth.forgotPasswordDescription"),
    email: t("auth.email"), send: t("auth.sendResetEmail"), loading: t("auth.loading"),
    codeSent: t("auth.recoveryCodeSent"), sendError: t("auth.resetEmailError"),
    verificationCode: t("auth.verificationCode"), verifyCode: t("auth.verifyCode"),
    resendCode: t("auth.resendCode"), invalidCode: t("auth.invalidRecoveryCode"),
    verifyError: t("auth.recoveryVerificationError"), newPassword: t("auth.newPassword"),
    confirmPassword: t("auth.confirmPassword"), updatePassword: t("auth.updatePassword"),
    passwordMismatch: t("auth.passwordMismatch"), updateError: t("auth.passwordUpdateError"),
    backToLogin: t("auth.backToLogin"),
  }} />;
}
