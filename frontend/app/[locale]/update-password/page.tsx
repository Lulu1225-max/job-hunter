import {redirect} from "next/navigation";

export default async function UpdatePasswordPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  redirect(`/${locale}/forgot-password`);
}
