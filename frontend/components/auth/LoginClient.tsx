"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useState} from "react";
import {loginDemo, loginWithPassword} from "@/lib/auth";

export function LoginClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function login() {
    setLoading(true);
    setError(null);
    try {
      await loginWithPassword(email, password);
      router.push(`/${locale}/dashboard`);
    } catch {
      setError(copy.error);
    } finally {
      setLoading(false);
    }
  }

  async function enterDemo() {
    setLoading(true);
    setError(null);
    try {
      await loginDemo();
      router.push(`/${locale}/dashboard`);
    } catch {
      setError(copy.demoError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-lg border border-line bg-white p-6 shadow-card">
      <h1 className="text-2xl font-semibold text-ink">{copy.title}</h1>
      <div className="mt-5 space-y-3">
        <input value={email} onChange={(event) => setEmail(event.target.value)} className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder={copy.email} type="email" />
        <input value={password} onChange={(event) => setPassword(event.target.value)} className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder={copy.password} type="password" />
        <button disabled={loading} onClick={login} className="block h-10 w-full rounded-md bg-brand px-4 py-2 text-center text-sm font-medium text-white shadow-card hover:bg-blue-700 disabled:opacity-60">
          {loading ? copy.loading : copy.login}
        </button>
        <button disabled={loading} onClick={enterDemo} className="block h-10 w-full rounded-md border border-line bg-white px-4 py-2 text-center text-sm font-medium text-ink hover:border-brand hover:text-brand disabled:opacity-60">
          {copy.demo}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <p className="text-sm text-muted">
          {copy.noAccount} <Link className="font-medium text-brand" href={`/${locale}/register`}>{copy.register}</Link>
        </p>
      </div>
    </div>
  );
}
