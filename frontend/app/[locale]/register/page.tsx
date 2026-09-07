import Link from "next/link";
import {getDictionary, translate} from "@/lib/dictionaries";

export default async function RegisterPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const dictionary = await getDictionary(locale);
  const t = (key: string) => translate(dictionary, key);
  return (
    <div className="mx-auto max-w-md rounded-lg border border-line bg-white p-6 shadow-card">
      <h1 className="text-2xl font-semibold text-ink">{t("auth.register")}</h1>
      <div className="mt-5 space-y-3">
        <input className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder="Name" />
        <input className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder="Email" />
        <input className="h-10 w-full rounded-md border border-line px-3 text-sm" placeholder="Password" type="password" />
        <Link href={`/${locale}/profile`} className="block h-10 rounded-md bg-brand px-4 py-2 text-center text-sm font-medium text-white shadow-card hover:bg-blue-700">
          {t("auth.register")}
        </Link>
      </div>
    </div>
  );
}
