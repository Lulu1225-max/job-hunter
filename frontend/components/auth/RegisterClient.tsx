"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useState} from "react";
import {registerWithPassword} from "@/lib/auth";

export function RegisterClient({locale, copy}: {locale: string; copy: Record<string, string>}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function register() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const session = await registerWithPassword(name, email, password);
      if (session) {
        router.push(`/${locale}/dashboard`);
      } else {
        setMessage(copy.confirmEmail);
      }
    } catch {
      setError(copy.error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-md rounded-lg border border-line bg-white p-6 shadow-card">
      <h1 className="text-2xl font-semibold text-ink">{copy.title}</h1>
      <div className="mt-5 space-y-3">
        <input value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder={copy.name} />
        <input value={email} onChange={(event) => setEmail(event.target.value)} className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder={copy.email} type="email" />
        <input value={password} onChange={(event) => setPassword(event.target.value)} className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder={copy.password} type="password" />
        <button disabled={loading} onClick={register} className="block h-10 w-full rounded-md bg-brand px-4 py-2 text-center text-sm font-medium text-white shadow-card hover:bg-blue-700 disabled:opacity-60">
          {loading ? copy.loading : copy.register}
        </button>
        {message && <p className="text-sm text-emerald-700">{message}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <p className="text-sm text-muted">
          {copy.hasAccount} <Link className="font-medium text-brand" href={`/${locale}/login`}>{copy.login}</Link>
        </p>
      </div>
    </div>
  );
}
