__all__ = ["industry_context_filter"]

import csv
import os
from pathlib import Path
from typing import Any


def industry_context_filter(subject: str = "", industry: str = "", sector: str = "", account_table: str = "account") -> dict:
    """Return deterministic industry/sector context for account-level analysis."""
    try:
        accounts = _read_csv_table(account_table)
    except RuntimeError as e:
        return {
            "resolvedAccount": None,
            "industryContext": None,
            "matchedAccounts": [],
            "sourceCoverage": {
                "Dataverse": {"status": "UNAVAILABLE", "reason": str(e)},
                "GraphWise": {"status": "EY_VALIDATE", "reason": "Wire GraphWise or governed taxonomy resolver for cross-source industry terminology."},
                "LENS": {"status": "EY_VALIDATE", "reason": "Wire LENS account profile and sector classification for EY validation."},
                "Discover": {"status": "EY_VALIDATE", "reason": "Wire Discover/CaaS benchmarks and sector market signals for EY validation."},
            },
            "validation": [{"id": "IC1", "status": "UNAVAILABLE", "note": "account source unavailable"}],
            "source_material": "crm-copilot-skills-sandbox/industry-context-filter/SKILL.md",
        }

    resolved = _resolve_account(accounts, subject) if subject else None
    criteria = _criteria(resolved, industry, sector)
    if not criteria:
        return {
            "resolvedAccount": _public_account(resolved) if resolved else None,
            "industryContext": None,
            "matchedAccounts": [],
            "sourceCoverage": {"Dataverse": {"status": "MATCHED", "table": account_table, "rows": len(accounts)}},
            "validation": [{"id": "IC1", "status": "FAIL", "note": "Provide an account, industry, or sector. Do not infer context from missing classification."}],
            "source_material": "crm-copilot-skills-sandbox/industry-context-filter/SKILL.md",
        }

    matched = [_public_account(row) for row in accounts if _matches(row, criteria)]
    matched.sort(key=lambda row: (row.get("displayName", ""), row.get("accountId", "")))
    counts = _counts(accounts, criteria)
    return {
        "resolvedAccount": _public_account(resolved) if resolved else None,
        "industryContext": {
            "industry": criteria.get("industry"),
            "sectorId": criteria.get("sectorId"),
            "sectorName": criteria.get("sectorName"),
            "subSectorId": criteria.get("subSectorId"),
            "subSectorName": criteria.get("subSectorName"),
            "contextRole": "filter_and_interpretation",
            "primaryDriver": False,
        },
        "matchedAccounts": matched[:100],
        "counts": counts,
        "sourceCoverage": {
            "Dataverse": {"status": "MATCHED", "table": account_table, "rows": len(accounts), "matchedRows": len(matched)},
            "GraphWise": {"status": "EY_VALIDATE", "reason": "Industry terminology normalization is represented as a required external resolver."},
            "LENS": {"status": "EY_VALIDATE", "reason": "Validate sector classification and peer/account context with LENS."},
            "Discover": {"status": "EY_VALIDATE", "reason": "Validate benchmark and market-signal context with Discover/CaaS."},
        },
        "validation": [
            {"id": "IC1", "status": "PASS" if criteria else "FAIL", "note": "industry/sector context was explicit or derived from resolved account classification"},
            {"id": "IC2", "status": "PASS" if criteria.get("sectorId") or criteria.get("subSectorId") else "UNAVAILABLE", "note": "sector/sub-sector classification present before filtering"},
            {"id": "IC3", "status": "EY_VALIDATE", "note": "GraphWise normalization must be wired before cross-source terminology claims"},
            {"id": "IC4", "status": "PASS", "note": "industry context is returned as context/filtering, not as sole recommendation driver"},
        ],
        "trace": {
            "criteria": criteria,
            "stableSort": ["displayName", "accountId"],
            "accountLevelFirst": True,
        },
        "source_material": "crm-copilot-skills-sandbox/industry-context-filter/SKILL.md",
    }


def _criteria(resolved: dict | None, industry: str, sector: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if resolved:
        out.update({
            "sectorId": _value(resolved, "ey_industrysectorid"),
            "sectorName": _value(resolved, "ey_industrysectoridname"),
            "subSectorId": _value(resolved, "ey_industrysubsectorid"),
            "subSectorName": _value(resolved, "ey_industrysubsectoridname"),
        })
    if sector:
        key = "sectorId" if _looks_like_id(sector) else "sectorName"
        out[key] = sector.strip()
    if industry:
        out["industry"] = industry.strip()
    return {k: v for k, v in out.items() if v}


def _matches(row: dict, criteria: dict[str, str]) -> bool:
    if criteria.get("subSectorId") and _value(row, "ey_industrysubsectorid") == criteria["subSectorId"]:
        return True
    if criteria.get("sectorId") and _value(row, "ey_industrysectorid") == criteria["sectorId"]:
        return True
    text = " ".join([
        _value(row, "ey_industrysectoridname"),
        _value(row, "ey_industrysubsectoridname"),
        _value(row, "industrycode"),
        _value(row, "sic"),
    ]).casefold()
    for key in ("sectorName", "subSectorName", "industry"):
        expected = criteria.get(key, "").casefold()
        if expected and expected in text:
            return True
    return False


def _counts(accounts: list[dict], criteria: dict[str, str]) -> dict[str, Any]:
    matched = [row for row in accounts if _matches(row, criteria)]
    by_channel: dict[str, int] = {}
    by_sector: dict[str, int] = {}
    by_subsector: dict[str, int] = {}
    for row in matched:
        _increment(by_channel, _value(row, "ey_channel") or "Unknown")
        _increment(by_sector, _value(row, "ey_industrysectoridname") or _value(row, "ey_industrysectorid") or "Unknown")
        _increment(by_subsector, _value(row, "ey_industrysubsectoridname") or _value(row, "ey_industrysubsectorid") or "Unknown")
    return {"matchedAccountCount": len(matched), "byChannel": by_channel, "bySector": by_sector, "bySubSector": by_subsector}


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _looks_like_id(value: str) -> bool:
    cleaned = value.strip()
    return len(cleaned) >= 12 and any(ch.isdigit() for ch in cleaned) and "-" in cleaned


def _resolve_account(rows: list[dict], identifier: str) -> dict | None:
    ident = identifier.strip().casefold()
    for col in ("accountid", "ey_mdmid", "ey_dunsnumber", "ey_gisultimatedunsnumber", "ey_globalultimateduns", "name"):
        matches = [row for row in rows if _value(row, col).casefold() == ident]
        if len(matches) == 1:
            return matches[0]
    matches = [row for row in rows if ident in _value(row, "name").casefold()]
    return matches[0] if len(matches) == 1 else None


def _public_account(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "accountId": _value(row, "accountid"),
        "displayName": _value(row, "name"),
        "channel": _value(row, "ey_channel"),
        "sectorId": _value(row, "ey_industrysectorid"),
        "sectorName": _value(row, "ey_industrysectoridname"),
        "subSectorId": _value(row, "ey_industrysubsectorid"),
        "subSectorName": _value(row, "ey_industrysubsectoridname"),
    }


def _value(row: dict, key: str) -> str:
    value = row.get(key, "")
    return "" if value is None or str(value).strip().casefold() in {"", "nan", "none", "null"} else str(value).strip()


def _read_csv_table(name: str) -> list[dict[str, str]]:
    for root in _data_roots():
        path = root / f"{name}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
    raise RuntimeError(f"UNAVAILABLE: table {name!r} not found. Set TOOLFORGE_DATA_DIR or mount CRM account data.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_synthetic"])
    return roots
