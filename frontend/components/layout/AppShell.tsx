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
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-line bg-white px-5 py-6 text-ink lg:block">
        <Link href={`/${locale}/dashboard`} className="focus-ring mb-10 flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="flex h-11 w-11 items-center justify-center rounded-md border border-line bg-paper shadow-sm">
            <BrandMark className="h-9 w-9" />
          </span>
          <span>
            <span className="block text-xl font-semibold tracking-[-0.025em]">Job Hunter</span>
            <span className="mt-0.5 block text-xs text-muted">{t("app.subtitle")}</span>
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
                className={`focus-ring flex h-11 items-center gap-3 rounded-md border px-3 text-sm ${
                  isActive ? "border-brand/20 bg-skysoft font-semibold text-brand shadow-sm" : "border-transparent text-muted hover:bg-paper hover:text-ink"
                }`}
              >
                <Icon className="h-4 w-4" />
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="lg:pl-72">
        <header className="sticky top-0 z-10 border-b border-line bg-paper/90 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:px-10">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-md border border-line bg-white shadow-sm">
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
                className="btn-secondary h-9 min-h-0 px-3"
              >
                <Languages className="h-4 w-4" />
                {otherLocale.toUpperCase()}
              </Link>
              {isSignedIn && !isAuthPage && (
                <button
                  onClick={handleLogout}
                  className="btn-secondary h-9 min-h-0 px-3"
                >
                  <LogOut className="h-4 w-4" />
                  {t("auth.logout")}
                </button>
              )}
            </div>
          </div>
          {!isAuthPage && <nav aria-label="Primary navigation" className="flex gap-1 overflow-x-auto border-t border-line px-4 py-2 lg:hidden">{navItems.map((item)=>{const Icon=item.icon;const href=`/${locale}${item.href}`;const active=pathname.startsWith(href);return <Link key={item.href} href={href} className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm ${active?"bg-skysoft font-semibold text-ink":"text-muted"}`}><Icon className="h-4 w-4"/>{t(item.labelKey)}</Link>})}</nav>}
        </header>
        <main className="mx-auto max-w-7xl px-6 py-10 lg:px-10 lg:py-14">{children}</main>
      </div>
    </div>
    </AuthGate>
  );
}
