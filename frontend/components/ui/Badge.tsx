import {cn} from "@/lib/utils";

const styles: Record<string, string> = {
  saved: "border-line bg-surface-muted text-muted",
  applied: "border-brand/15 bg-skysoft text-brand",
  oa: "border-brand/15 bg-skysoft text-brand",
  interview: "border-amber-200 bg-ambersoft text-amber-800",
  final_interview: "border-amber-200 bg-ambersoft text-amber-800",
  offer: "border-emerald-200 bg-mintsoft text-emerald-800",
  rejected: "border-red-200 bg-red-50 text-red-700",
  withdrawn: "border-line bg-surface-muted text-muted"
};

export function Badge({value, children}: {value: string; children: React.ReactNode}) {
  return <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold", styles[value] ?? styles.saved)}>{children}</span>;
}
