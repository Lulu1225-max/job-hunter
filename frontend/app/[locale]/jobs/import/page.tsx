"use client";

import {useMemo, useState} from "react";
import {usePathname} from "next/navigation";
import {Check, FileSpreadsheet, Search} from "lucide-react";
import {API_BASE_URL, authHeaders} from "@/lib/api";

type SheetPreview = {
  sheet_name: string;
  header_row: number | null;
  headers: string[];
  mapping: Record<string, string>;
  sample_rows: Record<string, unknown>[];
  confidence: number;
};

export default function JobImportPage() {
  const pathname = usePathname();
  const isZh = pathname.startsWith("/zh/");
  const copy = isZh
    ? {
        title: "Excel 职位导入",
        subtitle: "先检测工作表、表头和字段映射，确认后再导入。",
        filepath: "工作簿路径",
        detect: "检测",
        confirm: "确认导入",
        headerRow: "表头行",
        sourceColumn: "原始列",
        normalizedField: "标准字段",
        counts: {total_rows: "总行数", created: "新建", updated: "更新", skipped: "跳过", invalid: "无效"}
      }
    : {
        title: "Excel Job Import",
        subtitle: "Detect sheets, identify headers, preview mappings, and confirm before importing.",
        filepath: "Workbook path",
        detect: "Detect",
        confirm: "Confirm Import",
        headerRow: "Header row",
        sourceColumn: "Source column",
        normalizedField: "Normalized field",
        counts: {total_rows: "Rows", created: "Created", updated: "Updated", skipped: "Skipped", invalid: "Invalid"}
      };
  const [filepath, setFilepath] = useState("/Users/jilu/Desktop/JobHunter/sample-data/互联派名企校招2.xlsx");
  const [sheets, setSheets] = useState<SheetPreview[]>([]);
  const [selectedSheet, setSelectedSheet] = useState("");
  const [counts, setCounts] = useState<Record<string, number> | null>(null);

  const activeSheet = useMemo(() => sheets.find((sheet) => sheet.sheet_name === selectedSheet) ?? sheets[0], [sheets, selectedSheet]);

  async function previewImport() {
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/import`, {
      method: "POST",
      headers: {"Content-Type": "application/json", ...authHeaders()},
      body: JSON.stringify({filepath})
    });
    const data = await response.json();
    setSheets(data.sheets ?? []);
    setSelectedSheet(data.sheets?.[0]?.sheet_name ?? "");
    setCounts(null);
  }

  async function confirmImport() {
    const response = await fetch(`${API_BASE_URL}/api/v1/jobs/import`, {
      method: "POST",
      headers: {"Content-Type": "application/json", ...authHeaders()},
      body: JSON.stringify({filepath, sheet_name: activeSheet?.sheet_name, confirm: true})
    });
    setCounts(await response.json());
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{copy.subtitle}</p>
      </div>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <label className="text-sm font-medium text-ink">{copy.filepath}</label>
        <div className="mt-2 flex flex-col gap-3 md:flex-row">
          <input value={filepath} onChange={(event) => setFilepath(event.target.value)} className="h-10 flex-1 rounded-md border border-line px-3 text-sm" />
          <button onClick={previewImport} className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-white px-4 text-sm font-medium text-ink hover:border-brand hover:text-brand">
            <Search className="h-4 w-4" />
            {copy.detect}
          </button>
        </div>
      </section>
      {sheets.length > 0 && (
        <section className="grid gap-5 lg:grid-cols-[260px_1fr]">
          <div className="rounded-lg border border-line bg-white p-3 shadow-card">
            {sheets.map((sheet) => (
              <button
                key={sheet.sheet_name}
                onClick={() => setSelectedSheet(sheet.sheet_name)}
                className={`mb-2 flex w-full items-center gap-3 rounded-md px-3 py-3 text-left text-sm ${
                  activeSheet?.sheet_name === sheet.sheet_name ? "bg-zinc-100 text-ink" : "text-muted hover:bg-zinc-50"
                }`}
              >
                <FileSpreadsheet className="h-4 w-4" />
                <span className="flex-1">{sheet.sheet_name}</span>
                <span>{Math.round(sheet.confidence * 100)}%</span>
              </button>
            ))}
          </div>
          <div className="rounded-lg border border-line bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold">{activeSheet?.sheet_name}</h2>
                <p className="mt-1 text-sm text-muted">{copy.headerRow}: {activeSheet?.header_row ?? "None"}</p>
              </div>
              <button onClick={confirmImport} className="focus-ring inline-flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-medium text-white shadow-card hover:bg-blue-700">
                <Check className="h-4 w-4" />
                {copy.confirm}
              </button>
            </div>
            <div className="mt-5 overflow-hidden rounded-lg border border-line">
              <table className="w-full text-left text-sm">
                <thead className="bg-skysoft text-ink">
                  <tr>
                    <th className="px-3 py-2">{copy.sourceColumn}</th>
                    <th className="px-3 py-2">{copy.normalizedField}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(activeSheet?.mapping ?? {}).map(([source, target]) => (
                    <tr key={source} className="border-t border-line">
                      <td className="px-3 py-2">{source}</td>
                      <td className="px-3 py-2 font-medium">{target}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
      {counts && (
        <section className="grid gap-3 md:grid-cols-5">
          {(["total_rows", "created", "updated", "skipped", "invalid"] as const).map((key) => (
            <div key={key} className="rounded-lg border border-line bg-white p-4 shadow-card">
              <div className="text-sm text-muted">{copy.counts[key]}</div>
              <div className="mt-1 text-2xl font-semibold">{counts[key]}</div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
