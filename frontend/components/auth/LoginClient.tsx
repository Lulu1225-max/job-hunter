"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useRef, useState} from "react";
import {loginDemo, loginWithPassword} from "@/lib/auth";
import {BrandMark} from "@/components/branding/BrandMark";

export function LoginClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const submissionInFlight = useRef(false);

  async function login() {
    if (submissionInFlight.current) return;
    submissionInFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      await loginWithPassword(email, password);
    } catch {
      setError(copy.error);
      return;
    } finally {
      submissionInFlight.current = false;
      setLoading(false);
    }
    setError(null);
    router.replace(`/${locale}/dashboard`);
  }

  async function enterDemo() {
    if (submissionInFlight.current) return;
    submissionInFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      await loginDemo();
    } catch {
      setError(copy.demoError);
      return;
    } finally {
      submissionInFlight.current = false;
      setLoading(false);
    }
    setError(null);
    router.replace(`/${locale}/dashboard`);
  }

  return (
    <div className="mx-auto max-w-md rounded-lg border border-line bg-white p-6 shadow-card">
      <div className="flex items-center gap-3">
        <BrandMark className="h-12 w-12" />
        <span className="text-xl font-semibold text-ink">Job Hunter</span>
      </div>
      <h1 className="mt-5 text-2xl font-semibold text-ink">{copy.title}</h1>
      <div className="mt-5 space-y-3">
        <label className="block text-sm font-medium text-ink">{copy.email}<input value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm" autoComplete="email" type="email" /></label>
        <label className="block text-sm font-medium text-ink">{copy.password}<input value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm" autoComplete="current-password" type="password" /></label>
        <button type="button" disabled={loading} onClick={login} className="block h-10 w-full rounded-md bg-brand px-4 py-2 text-center text-sm font-medium text-white shadow-card hover:bg-blue-700 disabled:opacity-60">
          {loading ? copy.loading : copy.login}
        </button>
        <button type="button" disabled={loading} onClick={enterDemo} className="block h-10 w-full rounded-md border border-line bg-white px-4 py-2 text-center text-sm font-medium text-ink hover:border-brand hover:text-brand disabled:opacity-60">
          {loading ? copy.loading : copy.demo}
        </button>
        <p className="rounded-md bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">{copy.demoWarning}</p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <p className="text-sm text-muted">
          {copy.noAccount} <Link className="font-medium text-brand" href={`/${locale}/register`}>{copy.register}</Link>
        </p>
      </div>
    </div>
  );
}
