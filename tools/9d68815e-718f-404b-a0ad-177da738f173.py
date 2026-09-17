__all__: list[str] = ["bucket_ey_fiscal_year"]

import csv
import os
from datetime import date
from pathlib import Path
from typing import Any


def bucket_ey_fiscal_year(date_value: str, as_of_date: str = "", window_years: int = 3, fiscal_calendar_table: str = "ey_fiscalyear") -> dict:
    """Map a date to an EY fiscal year using the FiscalCalendar reference table."""
    as_of = date.fromisoformat(as_of_date or date.today().isoformat())
    try:
        calendar = _read_fiscal_calendar(fiscal_calendar_table)
    except RuntimeError as e:
        return {
            "bucketedDate": {"status": "UNAVAILABLE", "date": date_value, "reason": str(e)},
            "currentFiscalYear": {"status": "UNAVAILABLE", "date": as_of.isoformat(), "reason": str(e)},
            "window": {"status": "UNAVAILABLE", "reason": str(e)},
            "queryRules": _query_rules(),
            "sourceCoverage": {"FiscalCalendar": {"status": "UNAVAILABLE", "reason": str(e)}},
            "as_of": as_of.isoformat(),
            "source_material": "crm-copilot-skills-sandbox/ey-fiscalyear/SKILL.md",
        }
    bucketed = _bucket(calendar, date.fromisoformat(date_value))
    current = _bucket(calendar, as_of)
    window = _window(calendar, current, window_years)
    return {
        "bucketedDate": bucketed,
        "currentFiscalYear": current,
        "window": window,
        "queryRules": _query_rules(),
        "sourceCoverage": {"FiscalCalendar": {"status": "MATCHED", "rows": len(calendar), "table": fiscal_calendar_table}},
        "as_of": as_of.isoformat(),
        "source_material": "crm-copilot-skills-sandbox/ey-fiscalyear/SKILL.md",
    }


def _read_fiscal_calendar(table: str) -> list[dict[str, Any]]:
    rows = _read_csv_table(table)
    out = []
    for row in rows:
        fy = row.get("fy_id") or row.get("FiscalYearId")
        start = row.get("fy_start_date") or row.get("FiscalYearStartDt")
        end = row.get("fy_end_date") or row.get("FiscalYearEndDt")
        if fy and start and end:
            out.append({"fy_id": str(fy), "start": date.fromisoformat(str(start)[:10]), "end": date.fromisoformat(str(end)[:10])})
    if not out:
        raise ValueError("FiscalCalendar table exists but did not contain fiscal year id/start/end columns.")
    return sorted(out, key=lambda r: int(str(r["fy_id"]).replace("FY", "")))


def _query_rules() -> dict[str, str]:
    return {
        "join": "date_field >= FiscalYearStartDt AND date_field <= FiscalYearEndDt",
        "wonSalesDateField": "opportunity.ey_effectiveclosedate",
        "frameworkAgreementExclusion": "ey_opportunitytypecode <> 100000004",
        "nullDateBehavior": "UNAVAILABLE",
    }


def _bucket(calendar: list[dict[str, Any]], value: date) -> dict:
    for row in calendar:
        if row["start"] <= value <= row["end"]:
            return {
                "status": "MATCHED",
                "date": value.isoformat(),
                "fiscalYearId": row["fy_id"],
                "fiscalYearStart": row["start"].isoformat(),
                "fiscalYearEnd": row["end"].isoformat(),
            }
    return {"status": "UNAVAILABLE", "date": value.isoformat(), "reason": "outside_fiscal_calendar_range"}


def _window(calendar: list[dict[str, Any]], current: dict, window_years: int) -> dict:
    if current.get("status") != "MATCHED":
        return {"status": "UNAVAILABLE", "reason": "current_fiscal_year_unavailable"}
    current_num = int(str(current["fiscalYearId"]).replace("FY", ""))
    keep = [r for r in calendar if current_num - max(1, window_years) + 1 <= int(str(r["fy_id"]).replace("FY", "")) <= current_num]
    if not keep:
        return {"status": "UNAVAILABLE", "reason": "window_outside_fiscal_calendar"}
    return {"status": "MATCHED", "fiscalYears": [r["fy_id"] for r in keep], "start": keep[0]["start"].isoformat(), "end": keep[-1]["end"].isoformat()}


def _read_csv_table(name: str) -> list[dict[str, str]]:
    for root in _data_roots():
        path = root / f"{name}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
    raise RuntimeError(f"UNAVAILABLE: table {name!r} not found. Set TOOLFORGE_DATA_DIR or mount the ontology/reference CSVs.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_REFERENCE_DATA_DIR", "EYBCS_REFERENCE_DATA_DIR", "TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_ontology_ext" / "csv"])
    return roots
