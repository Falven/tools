__all__ = ["ey_footprint_assessment"]

import csv
import os
from datetime import date
from pathlib import Path
from typing import Any


FRAMEWORK_AGREEMENT_CODE = "100000004"
WON_STATUS_CODES = {"1", "won", "closed"}
OPEN_STATUS_CODES = {"0", "open", "active"}


def ey_footprint_assessment(account: str, as_of_date: str = "", window_years: int = 3, include_active_pipeline: bool = True, include_lens_context: bool = True) -> dict:
    """Aggregate won sales by service line for a resolved account/corporate tree."""
    as_of = date.fromisoformat(as_of_date or date.today().isoformat())
    try:
        accounts = _read_csv_table("account")
        opportunities = _read_csv_table("opportunity")
        products = _read_csv_table("opportunityproduct")
        fiscal_years = _read_fiscal_calendar("ey_fiscalyear")
    except RuntimeError as e:
        return {
            "resolvedAccount": None,
            "fiscalWindow": {"status": "UNAVAILABLE", "reason": str(e)},
            "sourceCoverage": {
                "Dataverse": {"status": "UNAVAILABLE", "reason": str(e)},
                "LENS": {"status": "EY_VALIDATE" if include_lens_context else "SKIPPED", "reason": "Wire LENS MCP for account profile, ambition, EY Activity, Client Meeting Investment, and relationship context."},
            },
            "salesByServiceLine": [],
            "activePipelineByServiceLine": [],
            "validation": [{"id": "C1", "status": "UNAVAILABLE", "note": "Dataverse/account source unavailable"}, {"id": "C2", "status": "EY_VALIDATE", "note": "LENS source requires EY wiring"}],
            "source_material": "crm-copilot-skills-sandbox/ey-footprint-assessment/SKILL.md",
        }
    resolved = _resolve_account(accounts, account)
    if resolved is None:
        return {"resolvedAccount": None, "validation": [{"id": "C1", "status": "FAIL", "note": "target_not_found"}]}

    account_ids = _corporate_tree_account_ids(accounts, resolved)
    current = _bucket(fiscal_years, as_of)
    window = _window(fiscal_years, current, window_years)
    if window["status"] != "MATCHED":
        return {"resolvedAccount": _public_account(resolved, account_ids), "validation": [{"id": "C3", "status": "FAIL", "note": window["reason"]}]}

    won_opps = _filter_opportunities(opportunities, account_ids, WON_STATUS_CODES, window["start"], window["end"])
    joined = _join_products(won_opps, products)
    sales = _sales_by_service_line(joined, "wonSalesUsd")
    pipeline = _sales_by_service_line(_join_products(_filter_opportunities(opportunities, account_ids, OPEN_STATUS_CODES, None, None), products), "openPipelineUsd") if include_active_pipeline else []
    lens = {
        "status": "EY_VALIDATE" if include_lens_context else "SKIPPED",
        "reason": "Wire LENS MCP for account profile, ambition, EY Activity, Client Meeting Investment, and relationship context."
        if include_lens_context else "include_lens_context=false",
    }
    return {
        "resolvedAccount": _public_account(resolved, account_ids),
        "fiscalWindow": window,
        "defaultsApplied": {"wonOnly": True, "windowYears": window_years, "currency": "USD/base", "frameworkAgreementsExcluded": True},
        "sourceCoverage": {"Dataverse": {"status": "MATCHED", "tables": ["account", "opportunity", "opportunityproduct"]}, "LENS": lens},
        "salesByServiceLine": sales,
        "activePipelineByServiceLine": pipeline,
        "heatmapPayload": _heatmap_payload(_public_account(resolved, account_ids), window, sales),
        "validation": [
            {"id": "C1", "status": "PASS", "note": "target resolved to account/corporate tree"},
            {"id": "C2", "status": lens["status"], "note": lens["reason"]},
            {"id": "C3", "status": "PASS", "note": "fiscal window derived from fiscal calendar"},
            {"id": "C4", "status": "PASS", "note": "won opportunities only; framework agreements excluded; value basis opportunityproduct.priceperunit_base"},
            {"id": "C7", "status": "PASS", "note": "deterministic grouping and sorting applied"},
        ],
        "source_material": "crm-copilot-skills-sandbox/ey-footprint-assessment/SKILL.md",
    }


def _resolve_account(rows: list[dict], identifier: str) -> dict | None:
    ident = identifier.strip().casefold()
    for col in ("accountid", "ey_mdmid", "ey_dunsnumber", "ey_gisultimatedunsnumber", "ey_globalultimateduns", "name"):
        matches = [row for row in rows if _value(row, col).casefold() == ident]
        if len(matches) == 1:
            return matches[0]
    name_matches = [row for row in rows if ident in _value(row, "name").casefold()]
    return name_matches[0] if len(name_matches) == 1 else None


def _corporate_tree_account_ids(accounts: list[dict], row: dict) -> list[str]:
    account_id = _value(row, "accountid")
    duns = _value(row, "ey_dunsnumber")
    uduns = _value(row, "ey_gisultimatedunsnumber") or _value(row, "ey_globalultimateduns") or duns
    ids = {account_id}
    for account in accounts:
        if uduns and (_value(account, "ey_gisultimatedunsnumber") == uduns or _value(account, "ey_globalultimateduns") == uduns or _value(account, "ey_dunsnumber") == duns):
            ids.add(_value(account, "accountid"))
    return sorted(i for i in ids if i)


def _filter_opportunities(rows: list[dict], account_ids: list[str], statuses: set[str], start: str | None, end: str | None) -> list[dict]:
    out = []
    for row in rows:
        account_id = _value(row, "ey_clientparentaccountid") or _value(row, "accountid")
        if account_id not in account_ids:
            continue
        if _value(row, "ey_statuscode").casefold() not in statuses:
            continue
        if _value(row, "ey_opportunitytypecode") == FRAMEWORK_AGREEMENT_CODE:
            continue
        if start and end:
            closed = _value(row, "ey_effectiveclosedate")
            if not closed or not (start <= closed[:10] <= end):
                continue
        out.append(row)
    return out


def _join_products(opportunities: list[dict], products: list[dict]) -> list[dict]:
    opp_ids = {_value(row, "opportunityid") for row in opportunities}
    return [row for row in products if _value(row, "opportunityid") in opp_ids]


def _sales_by_service_line(rows: list[dict], amount_name: str) -> list[dict]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (_value(row, "ey_servicelineid"), _value(row, "ey_servicelineidname") or "Unknown")
        item = grouped.setdefault(key, {"serviceLineId": key[0], "serviceLine": key[1], amount_name: 0.0, "lineCount": 0, "dealIds": set()})
        item[amount_name] += _float(_value(row, "priceperunit_base")) or 0.0
        item["lineCount"] += 1
        item["dealIds"].add(_value(row, "opportunityid"))
    out = []
    for item in grouped.values():
        item["dealCount"] = len(item.pop("dealIds"))
        item[amount_name] = round(item[amount_name], 2)
        out.append(item)
    return sorted(out, key=lambda r: (-r[amount_name], r["serviceLine"]))


def _heatmap_payload(account: dict, window: dict, rows: list[dict]) -> dict:
    return {
        "tool": "render_heatmap",
        "title": f"EY Footprint Heatmap - {account.get('displayName', 'Account')}",
        "rows": [row["serviceLine"] for row in rows[:10]],
        "cols": [", ".join(window.get("fiscalYears", []))],
        "values": [[_penetration_score(float(row.get("wonSalesUsd", 0.0)))] for row in rows[:10]],
        "scale": "score",
    }


def _read_fiscal_calendar(table: str) -> list[dict[str, Any]]:
    out = []
    for row in _read_csv_table(table):
        fy = row.get("fy_id") or row.get("FiscalYearId")
        start = row.get("fy_start_date") or row.get("FiscalYearStartDt")
        end = row.get("fy_end_date") or row.get("FiscalYearEndDt")
        if fy and start and end:
            out.append({"fy_id": str(fy), "start": str(start)[:10], "end": str(end)[:10]})
    return sorted(out, key=lambda r: int(str(r["fy_id"]).replace("FY", "")))


def _bucket(calendar: list[dict], value: date) -> dict:
    value_s = value.isoformat()
    for row in calendar:
        if row["start"] <= value_s <= row["end"]:
            return {"status": "MATCHED", "fiscalYearId": row["fy_id"], "fiscalYearStart": row["start"], "fiscalYearEnd": row["end"]}
    return {"status": "UNAVAILABLE", "reason": "outside_fiscal_calendar_range"}


def _window(calendar: list[dict], current: dict, window_years: int) -> dict:
    if current.get("status") != "MATCHED":
        return {"status": "UNAVAILABLE", "reason": "current_fiscal_year_unavailable"}
    current_num = int(str(current["fiscalYearId"]).replace("FY", ""))
    keep = [r for r in calendar if current_num - max(1, window_years) + 1 <= int(str(r["fy_id"]).replace("FY", "")) <= current_num]
    return {"status": "MATCHED", "fiscalYears": [r["fy_id"] for r in keep], "start": keep[0]["start"], "end": keep[-1]["end"]} if keep else {"status": "UNAVAILABLE", "reason": "window_outside_fiscal_calendar"}


def _public_account(row: dict, account_ids: list[str]) -> dict:
    return {"accountId": _value(row, "accountid"), "displayName": _value(row, "name"), "duns": _value(row, "ey_dunsnumber"), "globalUltimateDuns": _value(row, "ey_gisultimatedunsnumber") or _value(row, "ey_globalultimateduns"), "channel": _value(row, "ey_channel"), "corporateTreeAccountCount": len(account_ids)}


def _penetration_score(value: float) -> int:
    if value <= 0:
        return 1
    if value < 1_000_000:
        return 2
    if value < 5_000_000:
        return 3
    return 4


def _float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value(row: dict, key: str) -> str:
    value = row.get(key, "")
    return "" if value is None or str(value).strip().casefold() in {"", "nan", "none", "null"} else str(value).strip()


def _read_csv_table(name: str) -> list[dict[str, str]]:
    for root in _data_roots():
        path = root / f"{name}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
    raise RuntimeError(f"UNAVAILABLE: table {name!r} not found. Set TOOLFORGE_DATA_DIR or mount CRM/Fiscal data.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR", "TOOLFORGE_REFERENCE_DATA_DIR", "EYBCS_REFERENCE_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    for root in list(roots):
        roots.append(root.parent / "d365_ontology_ext" / "csv")
        roots.append(root.parent / "d365_synthetic")
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_synthetic", Path.cwd() / "data" / "d365_ontology_ext" / "csv"])
    return roots
