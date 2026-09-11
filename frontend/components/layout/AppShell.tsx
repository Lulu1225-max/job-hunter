"use client";

import Link from "next/link";
import {usePathname, useRouter} from "next/navigation";
import {useTranslations} from "next-intl";
import {Languages, LogOut} from "lucide-react";
import {navItems} from "@/lib/navigation";
import {AuthGate} from "@/components/auth/AuthGate";
import {getSession, logout, subscribeToAuthChanges} from "@/lib/auth";
import {useEffect, useState} from "react";
import {BrandMark} from "@/components/branding/BrandMark";

export function AppShell({children, locale}: {children: React.ReactNode; locale: string}) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations();
  const otherLocale = locale === "zh" ? "en" : "zh";
  const withoutLocale = pathname.replace(/^\/(en|zh)/, "") || "/dashboard";
  const isAuthPage = withoutLocale.startsWith("/login") || withoutLocale.startsWith("/register");
  const [isSignedIn, setIsSignedIn] = useState(false);

  useEffect(() => {
    function sync() {
      setIsSignedIn(Boolean(getSession()));
    }
    sync();
    return subscribeToAuthChanges(sync);
  }, []);

  async function handleLogout() {
    await logout();
    router.push(`/${locale}/login`);
  }

  return (
    <AuthGate locale={locale}>
      <div className="min-h-screen bg-paper">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-white px-4 py-5 text-ink lg:block">
        <Link href={`/${locale}/dashboard`} className="mb-8 flex items-start gap-3 rounded-lg bg-skysoft px-3 py-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white shadow-card">
            <BrandMark className="h-9 w-9" />
          </span>
          <span>
            <span className="block text-2xl font-semibold tracking-normal">Job Hunter</span>
            <span className="mt-1 block text-sm text-muted">{t("app.subtitle")}</span>
          </span>
        </Link>
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const href = `/${locale}${item.href}`;
            const isActive = pathname.startsWith(href);
            return (
              <Link
                key={item.href}
                href={href}
                className={`flex h-10 items-center gap-3 rounded-md border-l-2 px-3 text-sm transition ${
                  isActive ? "border-brand bg-skysoft font-semibold text-ink" : "border-transparent text-muted hover:bg-skysoft hover:text-ink"
                }`}
              >
                <Icon className="h-4 w-4" />
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-line bg-white/95 backdrop-blur">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-skysoft">
                <BrandMark className="h-8 w-8" />
              </span>
              <div>
              <div className="text-lg font-semibold text-ink">Job Hunter</div>
              <div className="text-xs text-muted">{t("app.chineseSubtitle")}</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href={`/${otherLocale}${withoutLocale}`}
                className="focus-ring flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm text-ink hover:border-brand hover:text-brand"
              >
                <Languages className="h-4 w-4" />
                {otherLocale.toUpperCase()}
              </Link>
              {isSignedIn && !isAuthPage && (
                <button
                  onClick={handleLogout}
                  className="focus-ring flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm text-ink hover:border-brand hover:text-brand"
                >
                  <LogOut className="h-4 w-4" />
                  {t("auth.logout")}
                </button>
              )}
            </div>
          </div>
          {!isAuthPage && <nav aria-label="Primary navigation" className="flex gap-1 overflow-x-auto border-t border-line px-4 py-2 lg:hidden">{navItems.map((item)=>{const Icon=item.icon;const href=`/${locale}${item.href}`;const active=pathname.startsWith(href);return <Link key={item.href} href={href} className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm ${active?"bg-skysoft font-semibold text-ink":"text-muted"}`}><Icon className="h-4 w-4"/>{t(item.labelKey)}</Link>})}</nav>}
        </header>
        <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
      </div>
    </div>
    </AuthGate>
  );
}
