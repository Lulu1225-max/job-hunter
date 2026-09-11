"use client";

import {usePathname, useRouter} from "next/navigation";
import {useEffect, useState} from "react";
import {restoreSession, startAutoRefresh, subscribeToAuthChanges} from "@/lib/auth";

const PUBLIC_PATHS = ["/login", "/register"];

export function AuthGate({children, locale}: {children: React.ReactNode; locale: string}) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const withoutLocale = pathname.replace(/^\/(en|zh)/, "") || "/dashboard";
  const isPublic = PUBLIC_PATHS.some((path) => withoutLocale.startsWith(path));

  useEffect(() => {
    let active = true;

    async function checkAuth() {
      setStatus("loading");
      const session = await restoreSession();
      if (!active) return;
      if (session) {
        setStatus("authenticated");
      } else {
        setStatus("unauthenticated");
        if (!isPublic) router.replace(`/${locale}/login`);
      }
    }

    void checkAuth();
    const unsubscribe = subscribeToAuthChanges(() => void checkAuth());
    const stopAutoRefresh = startAutoRefresh();
    return () => {
      active = false;
      unsubscribe();
      stopAutoRefresh();
    };
  }, [isPublic, locale, router]);

  if (!isPublic && status !== "authenticated") {
    return <main className="mx-auto max-w-6xl px-5 py-8 text-muted">Loading...</main>;
  }
  return children;
}
