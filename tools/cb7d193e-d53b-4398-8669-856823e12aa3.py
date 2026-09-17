__all__ = ["customer_similarity"]

import csv
import math
import os
from pathlib import Path


DIMENSION_WEIGHTS: dict[str, int] = {
    "industry_subsector": 20,
    "industry_sector": 10,
    "account_substatus": 10,
    "hq_geography": 16,
    "market_segment": 4,
    "company_size": 12,
}


def customer_similarity(target_account: str, top_n: int = 20, account_table: str = "account") -> dict:
    """Rank similar accounts from live/configured account data using deterministic dimensions."""
    try:
        accounts = _read_csv_table(account_table)
    except RuntimeError as e:
        return {
            "target": None,
            "candidates": [],
            "excludedCandidates": [],
            "sourceCoverage": {"CRM": {"status": "UNAVAILABLE", "reason": str(e)}, "LENS": {"status": "UNAVAILABLE", "reason": "LENS size track is not wired in this ToolForge function."}},
            "validation": [{"id": "C1", "status": "UNAVAILABLE", "note": "CRM account table unavailable"}, {"id": "C10", "status": "UNAVAILABLE", "note": "determinism cannot be tested until account data is mounted"}],
            "source_material": "crm-copilot-skills-sandbox/customer-similarity/SKILL.md",
        }
    target = _resolve_account(accounts, target_account)
    if target is None:
        return {"target": None, "candidates": [], "validation": [{"id": "C1", "status": "FAIL", "note": "target_not_found"}]}

    candidates = []
    excluded = []
    for row in accounts:
        if _value(row, "accountid") == _value(target, "accountid"):
            continue
        gate = _channel_gate(target, row)
        if gate != "PASS":
            excluded.append({"accountId": _value(row, "accountid"), "displayName": _value(row, "name"), "reason": gate})
            continue
        scores = _dimension_scores(target, row)
        available = {k: v for k, v in scores.items() if v is not None}
        if not available:
            continue
        denom = sum(DIMENSION_WEIGHTS[k] for k in available)
        numerator = sum(DIMENSION_WEIGHTS[k] * available[k] for k in available)
        candidates.append({
            "candidateAccountId": _value(row, "accountid"),
            "displayName": _value(row, "name"),
            "similarityScore": round(100 * numerator / denom, 2),
            "dimensionScores": available,
            "unavailableDimensions": [k for k, v in scores.items() if v is None],
            "explainability": {"denominator": denom, "points": {k: round(DIMENSION_WEIGHTS[k] * v, 3) for k, v in available.items()}},
        })
    candidates.sort(key=lambda r: (-r["similarityScore"], r["displayName"], r["candidateAccountId"]))
    return {
        "target": {"accountId": _value(target, "accountid"), "displayName": _value(target, "name"), "channel": _value(target, "ey_channel")},
        "candidates": candidates[: max(1, min(top_n, 100))],
        "excludedCandidates": excluded,
        "sourceCoverage": {"CRM": {"status": "MATCHED", "table": account_table, "rows": len(accounts)}, "LENS": {"status": "UNAVAILABLE", "reason": "LENS size track is not wired in this ToolForge function."}},
        "validation": [
            {"id": "C4", "status": "PASS", "note": "channel gate applied before ranking"},
            {"id": "C10", "status": "PASS", "note": "stable deterministic sort applied"},
            {"id": "C18", "status": "UNAVAILABLE", "note": "LENS/CRM two-track size logic not wired in this function"},
        ],
        "source_material": "crm-copilot-skills-sandbox/customer-similarity/SKILL.md",
    }


def _dimension_scores(target: dict, row: dict) -> dict[str, float | None]:
    return {
        "industry_subsector": _exact(target, row, "ey_industrysubsectorid"),
        "industry_sector": _exact(target, row, "ey_industrysectorid"),
        "account_substatus": _exact(target, row, "ey_accountsegmentsubstatusid"),
        "hq_geography": _geo_ladder(target, row),
        "market_segment": _exact(target, row, "ey_hqmarketsegmentid"),
        "company_size": _company_size(target, row),
    }


def _resolve_account(rows: list[dict], identifier: str) -> dict | None:
    ident = identifier.strip().casefold()
    for col in ("accountid", "ey_mdmid", "ey_dunsnumber", "ey_gisultimatedunsnumber", "ey_globalultimateduns", "name"):
        matches = [row for row in rows if _value(row, col).casefold() == ident]
        if len(matches) == 1:
            return matches[0]
    name_matches = [row for row in rows if ident in _value(row, "name").casefold()]
    return name_matches[0] if len(name_matches) == 1 else None


def _channel_gate(target: dict, row: dict) -> str:
    target_channel = _value(target, "ey_channel")
    candidate_channel = _value(row, "ey_channel")
    if not target_channel or not candidate_channel:
        return "UNRESOLVED_CHANNEL"
    return "PASS" if target_channel == candidate_channel else "SUPPRESS_CHANNEL_MISMATCH"


def _exact(a: dict, b: dict, col: str) -> float | None:
    av, bv = _value(a, col), _value(b, col)
    if not av or not bv:
        return None
    return 1.0 if av == bv else 0.0


def _geo_ladder(a: dict, b: dict) -> float | None:
    for col, score in (("ey_countryid", 1.0), ("ey_hqmarketsbusinessunitid", 0.75), ("ey_hqmarketsregionid", 0.5), ("ey_hqareaid", 0.25)):
        av, bv = _value(a, col), _value(b, col)
        if av and bv and av == bv:
            return score
    return 0.0


def _company_size(a: dict, b: dict) -> float | None:
    av, bv = _float(_value(a, "numberofemployees") or _value(a, "ey_annualrevenue")), _float(_value(b, "numberofemployees") or _value(b, "ey_annualrevenue"))
    if not av or not bv or av <= 0 or bv <= 0:
        return None
    return round(1 - min(1.0, abs(math.log10(av) - math.log10(bv)) / 2), 3)


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
    raise RuntimeError(f"UNAVAILABLE: table {name!r} not found. Set TOOLFORGE_DATA_DIR or mount CRM account data.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_synthetic"])
    return roots
