"use client";

import {usePathname, useRouter} from "next/navigation";
import {useEffect, useState} from "react";
import {getSession} from "@/lib/auth";

const PUBLIC_PATHS = ["/login", "/register"];

export function AuthGate({children, locale}: {children: React.ReactNode; locale: string}) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const withoutLocale = pathname.replace(/^\/(en|zh)/, "") || "/dashboard";
  const isPublic = PUBLIC_PATHS.some((path) => withoutLocale.startsWith(path));

  useEffect(() => {
    function checkAuth() {
      if (!isPublic && !getSession()) {
        router.replace(`/${locale}/login`);
        return;
      }
      setReady(true);
    }
    checkAuth();
    window.addEventListener("jobpilot-auth-change", checkAuth);
    return () => window.removeEventListener("jobpilot-auth-change", checkAuth);
  }, [isPublic, locale, router]);

  if (!isPublic && !ready) {
    return <main className="mx-auto max-w-6xl px-5 py-8 text-muted">Loading...</main>;
  }
  return children;
}
