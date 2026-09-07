from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.utils.matching import source_fingerprint
from app.utils.normalization import canonical_job_type, display_text, normalize_text, parse_date


CANONICAL_FIELDS = {
    "company": {"公司名称", "公司简称", "企业", "企业名称", "company", "employer"},
    "role": {"岗位名称", "职位", "role", "job title", "position", "title"},
    "job_url": {"投递链接", "职位链接", "投递方式", "job url", "url", "link", "apply link"},
    "location": {"地区", "base地", "base 地", "location", "city"},
    "description": {"职位画像", "岗位要求", "jd", "job description", "description", "requirements"},
    "deadline": {"网申截止时间", "截止日期", "deadline", "close date", "closing date"},
    "job_type": {"招聘类型", "job type", "type"},
    "industry": {"行业", "industry"},
    "graduation_cohort": {"届次", "graduation cohort", "cohort"},
    "application_open_date": {"网申开始时间", "上线日期", "open date", "start date"},
    "salary": {"薪资", "salary", "compensation"},
}

REQUIRED_FIELDS = {"company"}


@dataclass(frozen=True)
class SheetPreview:
    sheet_name: str
    header_row: int | None
    headers: list[str]
    mapping: dict[str, str]
    sample_rows: list[dict[str, Any]]
    confidence: float


@dataclass(frozen=True)
class NormalizedJobRow:
    source: str
    company: str
    role: str | None = None
    location: str | None = None
    job_url: str | None = None
    salary: str | None = None
    description: str | None = None
    industry: str | None = None
    job_type: str | None = None
    application_open_date: str | None = None
    deadline: str | None = None
    graduation_cohort: str | None = None
    technical_skills: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    source_hash: str = ""


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    reason: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ImportPreview:
    filename: str
    sheets: list[SheetPreview]


@dataclass(frozen=True)
class ImportResult:
    total_rows: int
    created: int
    updated: int
    skipped: int
    invalid: int
    jobs: list[NormalizedJobRow]
    issues: list[ImportIssue]


def detect_header_row(rows: list[list[Any]]) -> int | None:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows[:12]):
        labels = [normalize_text(cell) for cell in row if display_text(cell)]
        score = 0
        for aliases in CANONICAL_FIELDS.values():
            normalized_aliases = {normalize_text(alias) for alias in aliases}
            score += sum(1 for label in labels if label in normalized_aliases)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index if best_score >= 2 else None


def detect_columns(headers: list[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized_headers = [(str(header), normalize_text(header)) for header in headers if display_text(header)]
    for canonical, aliases in CANONICAL_FIELDS.items():
        normalized_aliases = {normalize_text(alias) for alias in aliases}
        for original, normalized in normalized_headers:
            if normalized in normalized_aliases or any(alias in normalized for alias in normalized_aliases):
                mapping[original] = canonical
                break
    return mapping


def preview_workbook(path: str | Path) -> ImportPreview:
    workbook_path = Path(path)
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    previews: list[SheetPreview] = []
    for ws in wb.worksheets:
        sample = [list(row) for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 15), values_only=True)]
        header_index = detect_header_row(sample)
        if header_index is None:
            previews.append(SheetPreview(ws.title, None, [], {}, [], 0))
            continue
        headers = [display_text(cell) or "" for cell in sample[header_index]]
        mapping = detect_columns(headers)
        mapped_rows = []
        for row in sample[header_index + 1 : header_index + 6]:
            raw = {headers[i]: row[i] if i < len(row) else None for i in range(len(headers)) if headers[i]}
            mapped_rows.append({mapping[key]: value for key, value in raw.items() if key in mapping and display_text(value)})
        confidence = round(len(set(mapping.values())) / max(len(CANONICAL_FIELDS), 1), 2)
        previews.append(SheetPreview(ws.title, header_index + 1, headers, mapping, mapped_rows, confidence))
    return ImportPreview(filename=workbook_path.name, sheets=previews)


def normalize_row(source: str, raw: dict[str, Any], row_number: int) -> tuple[NormalizedJobRow | None, ImportIssue | None]:
    company = display_text(raw.get("company"))
    role = display_text(raw.get("role"))
    job_url = display_text(raw.get("job_url"))
    description = display_text(raw.get("description"))
    if not company:
        return None, ImportIssue(row_number, "Missing company", raw)
    if not any([role, job_url, description]):
        return None, ImportIssue(row_number, "Missing role, job URL, or description", raw)

    deadline = parse_date(raw.get("deadline"))
    open_date = parse_date(raw.get("application_open_date"))
    row = NormalizedJobRow(
        source=source,
        company=company,
        role=role,
        location=display_text(raw.get("location")),
        job_url=job_url,
        salary=display_text(raw.get("salary")),
        description=description,
        industry=display_text(raw.get("industry")),
        job_type=canonical_job_type(raw.get("job_type")),
        application_open_date=open_date.isoformat() if open_date else None,
        deadline=deadline.isoformat() if deadline else None,
        graduation_cohort=display_text(raw.get("graduation_cohort")),
        source_hash=source_fingerprint([company, role, raw.get("location"), job_url]),
    )
    return row, None


def import_sheet(path: str | Path, sheet_name: str, existing_hashes: set[str] | None = None) -> ImportResult:
    existing_hashes = existing_hashes or set()
    preview = preview_workbook(path)
    sheet_preview = next((sheet for sheet in preview.sheets if sheet.sheet_name == sheet_name), None)
    if sheet_preview is None or sheet_preview.header_row is None:
        return ImportResult(0, 0, 0, 0, 0, [], [ImportIssue(0, "No detectable header row", {})])

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    headers = [display_text(cell.value) or "" for cell in ws[sheet_preview.header_row]]
    mapping = detect_columns(headers)
    jobs: list[NormalizedJobRow] = []
    issues: list[ImportIssue] = []
    created = updated = skipped = 0
    for row_number, values in enumerate(
        ws.iter_rows(min_row=sheet_preview.header_row + 1, values_only=True),
        start=sheet_preview.header_row + 1,
    ):
        raw_by_header = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers)) if headers[i]}
        mapped = {mapping[key]: value for key, value in raw_by_header.items() if key in mapping}
        if not any(display_text(value) for value in mapped.values()):
            skipped += 1
            continue
        job, issue = normalize_row(Path(path).name, mapped, row_number)
        if issue:
            issues.append(issue)
            continue
        assert job is not None
        if job.source_hash in existing_hashes:
            updated += 1
        else:
            created += 1
            existing_hashes.add(job.source_hash)
        jobs.append(job)
    return ImportResult(
        total_rows=created + updated + skipped + len(issues),
        created=created,
        updated=updated,
        skipped=skipped,
        invalid=len(issues),
        jobs=jobs,
        issues=issues,
    )
