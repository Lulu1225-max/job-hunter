"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useState} from "react";
import {BrandMark} from "@/components/branding/BrandMark";
import {RecoveryOtpError, RecoverySessionError, requestPasswordReset, updatePasswordWithRecovery, verifyPasswordRecoveryOtp} from "@/lib/auth";

export function ForgotPasswordClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const router = useRouter();
  const [stage, setStage] = useState<"email" | "otp" | "password">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function sendResetEmail() {
    if (!email.trim() || loading) return;
    setLoading(true);
    setNotice(null);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setStage("otp");
      setNotice(copy.codeSent);
    } catch {
      setError(copy.sendError);
    } finally {
      setLoading(false);
    }
  }

  async function verifyCode() {
    if (!email.trim() || !code.trim() || loading) return;
    setLoading(true);
    setNotice(null);
    setError(null);
    try {
      await verifyPasswordRecoveryOtp(email.trim(), code.trim());
      setStage("password");
    } catch (caught) {
      setError(caught instanceof RecoveryOtpError && ["otp_expired", "otp_invalid"].includes(caught.errorType)
        ? copy.invalidCode
        : copy.verifyError);
    } finally {
      setLoading(false);
    }
  }

  async function updatePassword() {
    if (!password || !confirmation || loading) return;
    setError(null);
    if (password !== confirmation) {
      setError(copy.passwordMismatch);
      return;
    }
    setLoading(true);
    try {
      await updatePasswordWithRecovery(password);
      router.replace(`/${locale}/login`);
    } catch (caught) {
      setError(caught instanceof RecoverySessionError ? copy.invalidCode : copy.updateError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-lg border border-line bg-white p-6 shadow-card">
      <div className="flex items-center gap-3"><BrandMark className="h-12 w-12" /><span className="text-xl font-semibold text-ink">Job Hunter</span></div>
      <h1 className="mt-5 text-2xl font-semibold text-ink">{copy.title}</h1>
      <p className="mt-2 text-sm leading-6 text-muted">{copy.description}</p>
      <div className="mt-5 space-y-3">
        {stage !== "password" && <label className="block text-sm font-medium text-ink">{copy.email}<input value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm" autoComplete="email" type="email" /></label>}
        {stage === "email" && <button type="button" disabled={loading || !email.trim()} onClick={sendResetEmail} className="btn-primary w-full disabled:opacity-60">{loading ? copy.loading : copy.send}</button>}
        {stage === "otp" && <>
          <label className="block text-sm font-medium text-ink">{copy.verificationCode}<input value={code} onChange={(event) => setCode(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm tracking-[0.2em]" autoComplete="one-time-code" inputMode="numeric" /></label>
          <button type="button" disabled={loading || !email.trim() || !code.trim()} onClick={verifyCode} className="btn-primary w-full disabled:opacity-60">{loading ? copy.loading : copy.verifyCode}</button>
          <button type="button" disabled={loading || !email.trim()} onClick={sendResetEmail} className="btn-secondary w-full disabled:opacity-60">{copy.resendCode}</button>
        </>}
        {stage === "password" && <>
          <label className="block text-sm font-medium text-ink">{copy.newPassword}<input value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm" autoComplete="new-password" type="password" /></label>
          <label className="block text-sm font-medium text-ink">{copy.confirmPassword}<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm" autoComplete="new-password" type="password" /></label>
          <button type="button" disabled={loading || !password || !confirmation} onClick={updatePassword} className="btn-primary w-full disabled:opacity-60">{loading ? copy.loading : copy.updatePassword}</button>
        </>}
        {notice && <p role="status" className="text-sm leading-6 text-emerald-700">{notice}</p>}
        {error && <p role="alert" className="text-sm leading-6 text-red-600">{error}</p>}
        <p className="text-sm text-muted"><Link className="font-medium text-brand hover:underline" href={`/${locale}/login`}>{copy.backToLogin}</Link></p>
      </div>
    </div>
  );
}
