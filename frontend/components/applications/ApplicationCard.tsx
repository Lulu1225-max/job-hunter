import {useTranslations} from "next-intl";
import Link from "next/link";
import {Badge} from "@/components/ui/Badge";
import {Trash2} from "lucide-react";

type ApplicationCardData = {
    id: string;
    company: string;
    role?: string | null;
    status: string;
    application_date?: string | null;
    deadline?: string | null;
};

type ApplicationCardProps = {
  application: ApplicationCardData;
  locale?: string;
  onStatusChange?: (id: string, status: string) => void;
  onDelete?: (application: ApplicationCardData) => void;
  deleteLabel?: string;
};

const statuses = ["applied", "oa", "interview", "offer", "rejected", "saved", "final_interview", "withdrawn"];

export function ApplicationCard({application, locale, onStatusChange, onDelete, deleteLabel}: ApplicationCardProps) {
  const t = useTranslations();
  const date = application.application_date || application.deadline;
  const body = (
    <>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-ink">{application.company}</h3>
          <p className="mt-2 line-clamp-1 text-muted">{application.role || t("applications.roleMissing")}</p>
        </div>
        <Badge value={application.status}>{t(`status.${application.status}`)}</Badge>
      </div>
      <p className="mt-5 text-sm text-muted">
        {date ? `${t("applications.date")}: ${date}` : t("applications.noDate")}
      </p>
      {application.deadline && <p className="mt-2 text-sm text-amber-700">{t("dashboard.deadlines")}: {application.deadline}</p>}
      {application.status === "interview" && (
        <div className="mt-4 inline-flex rounded-md bg-mintsoft px-3 py-2 text-sm font-medium text-emerald-700">
          {t("applications.prepareInterview")}
        </div>
      )}
    </>
  );

  return (
    <article className="rounded-lg border border-line bg-white p-5 shadow-card">
      {locale ? (
        <Link href={`/${locale}/applications/${application.id}`} className="block">
          {body}
        </Link>
      ) : (
        body
      )}
      {onStatusChange && (
        <select
          value={application.status}
          onChange={(event) => onStatusChange(application.id, event.target.value)}
          className="mt-4 h-9 w-full rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-blue-100"
        >
          {statuses.map((status) => (
            <option key={status} value={status}>{t(`status.${status}`)}</option>
          ))}
        </select>
      )}
      {onDelete && (
        <button type="button" onClick={() => onDelete(application)} className="mt-3 inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50">
          <Trash2 className="h-4 w-4" />
          {deleteLabel}
        </button>
      )}
    </article>
  );
}
