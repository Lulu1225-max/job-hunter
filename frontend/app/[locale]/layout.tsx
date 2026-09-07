import {NextIntlClientProvider} from "next-intl";
import type {ReactNode} from "react";
import {AppShell} from "@/components/layout/AppShell";
import {getDictionary} from "@/lib/dictionaries";

export default async function LocaleLayout({children, params}: {children: ReactNode; params: Promise<{locale: string}>}) {
  const {locale} = await params;
  const messages = await getDictionary(locale);

  return (
    <NextIntlClientProvider messages={messages}>
      <AppShell locale={locale}>{children}</AppShell>
    </NextIntlClientProvider>
  );
}
