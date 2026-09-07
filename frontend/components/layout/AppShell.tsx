"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useTranslations} from "next-intl";
import {Languages, PlaneTakeoff} from "lucide-react";
import {navItems} from "@/lib/navigation";

export function AppShell({children, locale}: {children: React.ReactNode; locale: string}) {
  const pathname = usePathname();
  const t = useTranslations();
  const otherLocale = locale === "zh" ? "en" : "zh";
  const withoutLocale = pathname.replace(/^\/(en|zh)/, "") || "/dashboard";

  return (
    <div className="min-h-screen bg-paper">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-white px-4 py-5 text-ink lg:block">
        <Link href={`/${locale}/dashboard`} className="mb-8 flex items-start gap-3 rounded-lg bg-skysoft px-3 py-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-brand text-white shadow-card">
            <PlaneTakeoff className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-2xl font-semibold tracking-normal">JobPilot</span>
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
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-skysoft text-brand">
                <PlaneTakeoff className="h-4 w-4" />
              </span>
              <div>
              <div className="text-lg font-semibold text-ink">JobPilot</div>
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
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
      </div>
    </div>
  );
}
