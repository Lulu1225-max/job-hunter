import {cn} from "@/lib/utils";

const styles: Record<string, string> = {
  saved: "bg-zinc-100 text-zinc-700",
  applied: "bg-blue-100 text-blue-700",
  oa: "bg-purple-100 text-purple-700",
  interview: "bg-amber-100 text-amber-800",
  final_interview: "bg-orange-100 text-orange-800",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  withdrawn: "bg-zinc-200 text-zinc-600"
};

export function Badge({value, children}: {value: string; children: React.ReactNode}) {
  return <span className={cn("rounded-full px-3 py-1 text-xs font-medium", styles[value] ?? styles.saved)}>{children}</span>;
}
