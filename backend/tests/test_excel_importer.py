from pathlib import Path

from app.utils.excel import import_sheet, preview_workbook


ROOT = Path(__file__).resolve().parents[2]


def test_preview_detects_non_first_header_row_in_sample_workbooks():
    preview = preview_workbook(ROOT / "smaple-data" / "互联派名企校招2.xlsx")
    official = next(sheet for sheet in preview.sheets if sheet.sheet_name == "官方校招")
    referral = next(sheet for sheet in preview.sheets if sheet.sheet_name == "名企直推")

    assert official.header_row == 2
    assert official.mapping["公司名称"] == "company"
    assert official.mapping["投递链接"] == "job_url"
    assert referral.mapping["企业"] == "company"
    assert referral.mapping["岗位名称"] == "role"
    assert referral.mapping["base地"] == "location"


def test_import_normalizes_rows_and_counts_updates_by_hash():
    path = ROOT / "smaple-data" / "互联派名企校招2.xlsx"
    result = import_sheet(path, "名企直推")
    assert result.created > 30
    assert result.invalid == 0
    assert result.jobs[0].company and result.jobs[0].role and result.jobs[0].source_hash
    updated = import_sheet(path, "名企直推", {job.source_hash for job in result.jobs})
    assert updated.updated == len(updated.jobs)
