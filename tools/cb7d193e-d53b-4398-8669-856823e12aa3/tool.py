__all__ = ["customer_similarity"]

import csv
import math
import os
from datetime import date
from pathlib import Path
from typing import Any


DIMENSION_WEIGHTS: dict[str, int] = {
    "industry_subsector": 20,
    "industry_sector": 10,
    "account_substatus": 10,
    "hq_geography": 16,
    "market_segment": 4,
    "company_size": 12,
    "service_line_footprint": 8,
    "service_line_revenue_mix": 5,
    "solution_footprint": 5,
    "field_of_play_footprint": 10,
}
FRAMEWORK_AGREEMENT_CODE = "100000004"
WON_STATUS_CODES = {"1", "won", "closed"}
ALLOWED_ORIGIN_CODES = {"Z08", "Z09", "z08", "z09"}


def customer_similarity(target_account: str, top_n: int = 20, account_table: str = "account") -> dict:
    """Rank similar accounts with deterministic, source-traceable scoring."""
    try:
        accounts = _read_csv_table(account_table)
    except RuntimeError as e:
        return _unavailable_result(target_account, {"CRM": {"status": "UNAVAILABLE", "reason": str(e)}})

    target = _resolve_account(accounts, target_account)
    if target is None:
        return {
            "target": None,
            "candidates": [],
            "excludedCandidates": [],
            "sourceCoverage": {"CRM": {"status": "MATCHED", "table": account_table, "rows": len(accounts)}},
            "validation": [{"id": "C1", "status": "FAIL", "note": "target_not_found_or_ambiguous"}],
            "trace": {"targetInput": target_account},
            "source_material": "crm-copilot-skills-sandbox/customer-similarity/SKILL.md",
        }

    fiscal = _load_fiscal_window()
    footprint = _load_footprints(accounts, fiscal.get("window"))
    band = _substatus_band(target)
    seed_rows, seed_trace = _candidate_seeds(accounts, target, band)
    schema_notes = _schema_notes(accounts)

    candidates = []
    excluded = []
    for row, seed in seed_rows:
        gate = _channel_gate(target, row)
        if gate != "PASS":
            excluded.append(_excluded(row, gate, seed))
            continue
        scores = _dimension_scores(target, row, footprint)
        available = {k: v for k, v in scores.items() if v is not None}
        if not available:
            excluded.append(_excluded(row, "NO_SCORABLE_DIMENSIONS", seed))
            continue
        denominator = sum(DIMENSION_WEIGHTS[k] for k in available)
        points = {k: round(DIMENSION_WEIGHTS[k] * available[k], 4) for k in available}
        numerator = sum(points.values())
        candidates.append({
            "candidateAccountId": _value(row, "accountid"),
            "displayName": _value(row, "name"),
            "similarityScore": round(100 * numerator / denominator, 2),
            "dimensionScores": available,
            "unavailableDimensions": [k for k, v in scores.items() if v is None],
            "explainability": {
                "seed": seed,
                "denominator": denominator,
                "points": points,
                "whatHelped": [k for k, v in available.items() if v > 0],
                "whatHeldBack": [k for k, v in available.items() if v == 0],
            },
        })

    candidates.sort(key=lambda r: (-r["similarityScore"], r["displayName"], r["candidateAccountId"]))
    top_n = max(1, min(int(top_n or 20), 100))
    footprint_status = footprint.get("sourceCoverage", {})
    return {
        "target": _public_account(target),
        "candidates": candidates[:top_n],
        "excludedCandidates": excluded,
        "sourceCoverage": {
            "CRM": {"status": "MATCHED", "table": account_table, "rows": len(accounts)},
            "FiscalCalendar": fiscal.get("sourceCoverage", {"status": "UNAVAILABLE"}),
            "Footprint": footprint_status,
            "LENS": {"status": "UNAVAILABLE", "reason": "LENS size track is not wired in this ToolForge function; CRM size fallback used where available."},
        },
        "validation": [
            {"id": "C1", "status": "PASS", "note": "target resolved to a single account row"},
            {"id": "C4", "status": "PASS", "note": "channel gate applied before ranking"},
            {"id": "C7", "status": "PASS", "note": "candidate scoring returns only PASS/UNAVAILABLE checks"},
            {"id": "C9", "status": "PASS", "note": "cohort generated from target classification seeds, not user-supplied peers"},
            {"id": "C10", "status": "PASS" if band["status"] == "MATCHED" else "UNAVAILABLE", "note": band["note"]},
            {"id": "C11", "status": "PASS", "note": "every ranked account includes score explainability"},
            {"id": "C18", "status": "UNAVAILABLE", "note": "LENS company-size track not wired; CRM size fallback used when available"},
        ],
        "trace": {
            "weights": DIMENSION_WEIGHTS,
            "candidateSeeds": seed_trace,
            "schemaNotes": schema_notes,
            "candidatePoolSize": len(seed_rows),
            "rankedCandidateCount": len(candidates),
            "fiscalWindow": fiscal.get("window"),
            "stableSort": ["-similarityScore", "displayName", "candidateAccountId"],
        },
        "source_material": "crm-copilot-skills-sandbox/customer-similarity/SKILL.md",
    }


def _unavailable_result(target_account: str, coverage: dict) -> dict:
    return {
        "target": None,
        "candidates": [],
        "excludedCandidates": [],
        "sourceCoverage": coverage,
        "validation": [{"id": "C1", "status": "UNAVAILABLE", "note": "CRM account source unavailable"}],
        "trace": {"targetInput": target_account},
        "source_material": "crm-copilot-skills-sandbox/customer-similarity/SKILL.md",
    }


def _candidate_seeds(accounts: list[dict], target: dict, band: dict) -> tuple[list[tuple[dict, str]], list[dict]]:
    seeds = [
        ("same_subsector", {"ey_industrysubsectorid": _value(target, "ey_industrysubsectorid")}),
        ("same_sector_market_segment", {"ey_industrysectorid": _value(target, "ey_industrysectorid"), "ey_hqmarketsegmentid": _value(target, "ey_hqmarketsegmentid")}),
        ("same_sector_business_unit", {"ey_industrysectorid": _value(target, "ey_industrysectorid"), "ey_hqmarketsbusinessunitid": _value(target, "ey_hqmarketsbusinessunitid")}),
        ("same_sector", {"ey_industrysectorid": _value(target, "ey_industrysectorid")}),
    ]
    seen: set[str] = set()
    out: list[tuple[dict, str]] = []
    trace = []
    for name, predicates in seeds:
        rows = []
        for row in sorted(accounts, key=lambda r: (_value(r, "ey_mdmid"), _value(r, "name"), _value(r, "accountid"))):
            account_id = _value(row, "accountid")
            if not account_id or account_id == _value(target, "accountid") or account_id in seen:
                continue
            if not _is_global_ultimate_like(row):
                continue
            if not _in_substatus_band(row, band):
                continue
            if all(not expected or _value(row, key) == expected for key, expected in predicates.items()):
                rows.append(row)
        for row in rows[:25]:
            seen.add(_value(row, "accountid"))
            out.append((row, name))
        trace.append({"seed": name, "predicates": predicates, "returned": len(rows), "kept": min(len(rows), 25)})
    return out, trace


def _dimension_scores(target: dict, row: dict, footprint: dict) -> dict[str, float | None]:
    target_fp = footprint.get("byAccount", {}).get(_value(target, "accountid"), {})
    row_fp = footprint.get("byAccount", {}).get(_value(row, "accountid"), {})
    return {
        "industry_subsector": _exact(target, row, "ey_industrysubsectorid"),
        "industry_sector": _exact(target, row, "ey_industrysectorid"),
        "account_substatus": _exact(target, row, "ey_accountsegmentsubstatusid"),
        "hq_geography": _geo_ladder(target, row),
        "market_segment": _exact(target, row, "ey_hqmarketsegmentid"),
        "company_size": _company_size(target, row),
        "service_line_footprint": _jaccard(target_fp.get("serviceLineIds", set()), row_fp.get("serviceLineIds", set())),
        "service_line_revenue_mix": _cosine(target_fp.get("serviceLineAmounts", {}), row_fp.get("serviceLineAmounts", {})),
        "solution_footprint": _jaccard(target_fp.get("solutionIds", set()), row_fp.get("solutionIds", set())),
        "field_of_play_footprint": _jaccard(target_fp.get("fieldOfPlayIds", set()), row_fp.get("fieldOfPlayIds", set())),
    }


def _load_footprints(accounts: list[dict], window: dict | None) -> dict:
    try:
        opportunities = _read_csv_table("opportunity")
        products = _read_csv_table("opportunityproduct")
    except RuntimeError as e:
        return {"byAccount": {}, "sourceCoverage": {"status": "UNAVAILABLE", "reason": str(e)}}
    if not window or window.get("status") != "MATCHED":
        return {"byAccount": {}, "sourceCoverage": {"status": "UNAVAILABLE", "reason": "fiscal_window_unavailable"}}
    account_to_parent = {_value(row, "accountid"): _value(row, "accountid") for row in accounts}
    qualifying_opp_ids: dict[str, str] = {}
    for opp in opportunities:
        if _value(opp, "ey_statuscode").casefold() not in WON_STATUS_CODES:
            continue
        origin = _value(opp, "ey_origintypecode")
        if origin and origin not in ALLOWED_ORIGIN_CODES:
            continue
        if _value(opp, "ey_opportunitytypecode") == FRAMEWORK_AGREEMENT_CODE:
            continue
        closed = _value(opp, "ey_effectiveclosedate")[:10]
        if not closed or not (window["start"] <= closed <= window["end"]):
            continue
        account_id = _value(opp, "ey_clientparentaccountid") or _value(opp, "accountid")
        if account_id in account_to_parent:
            qualifying_opp_ids[_value(opp, "opportunityid")] = account_id

    by_account: dict[str, dict[str, Any]] = {}
    for product in products:
        account_id = qualifying_opp_ids.get(_value(product, "opportunityid"))
        if not account_id:
            continue
        item = by_account.setdefault(account_id, {"serviceLineIds": set(), "serviceLineAmounts": {}, "solutionIds": set(), "fieldOfPlayIds": set()})
        service_line = _value(product, "ey_servicelineid")
        solution = _value(product, "ey_solutionid")
        fop = _value(product, "ey_buyerbasedfieldofplayid")
        amount = _float(_value(product, "priceperunit_base")) or 0.0
        if service_line:
            item["serviceLineIds"].add(service_line)
            item["serviceLineAmounts"][service_line] = item["serviceLineAmounts"].get(service_line, 0.0) + amount
        if solution:
            item["solutionIds"].add(solution)
        if fop:
            item["fieldOfPlayIds"].add(fop)
    return {
        "byAccount": by_account,
        "sourceCoverage": {"status": "MATCHED", "opportunities": len(opportunities), "products": len(products), "qualifiedOpportunities": len(qualifying_opp_ids)},
    }


def _load_fiscal_window() -> dict:
    try:
        calendar = _read_fiscal_calendar("ey_fiscalyear")
    except RuntimeError as e:
        return {"window": None, "sourceCoverage": {"status": "UNAVAILABLE", "reason": str(e)}}
    current = _bucket(calendar, date.today())
    window = _window(calendar, current, 3)
    return {"window": window, "sourceCoverage": {"status": "MATCHED", "rows": len(calendar)}}


def _read_fiscal_calendar(table: str) -> list[dict[str, Any]]:
    out = []
    for row in _read_csv_table(table):
        fy = row.get("fy_id") or row.get("FiscalYearId")
        start = row.get("fy_start_date") or row.get("FiscalYearStartDt")
        end = row.get("fy_end_date") or row.get("FiscalYearEndDt")
        if fy and start and end:
            out.append({"fy_id": str(fy), "start": date.fromisoformat(str(start)[:10]), "end": date.fromisoformat(str(end)[:10])})
    if not out:
        raise RuntimeError(f"UNAVAILABLE: table {table!r} did not contain fiscal year id/start/end columns.")
    return sorted(out, key=lambda r: int(str(r["fy_id"]).replace("FY", "")))


def _bucket(calendar: list[dict[str, Any]], value: date) -> dict:
    for row in calendar:
        if row["start"] <= value <= row["end"]:
            return {"status": "MATCHED", "fiscalYearId": row["fy_id"], "fiscalYearStart": row["start"].isoformat(), "fiscalYearEnd": row["end"].isoformat()}
    return {"status": "UNAVAILABLE", "reason": "outside_fiscal_calendar_range"}


def _window(calendar: list[dict[str, Any]], current: dict, window_years: int) -> dict:
    if current.get("status") != "MATCHED":
        return {"status": "UNAVAILABLE", "reason": "current_fiscal_year_unavailable"}
    current_num = int(str(current["fiscalYearId"]).replace("FY", ""))
    keep = [r for r in calendar if current_num - max(1, window_years) + 1 <= int(str(r["fy_id"]).replace("FY", "")) <= current_num]
    return {"status": "MATCHED", "fiscalYears": [r["fy_id"] for r in keep], "start": keep[0]["start"].isoformat(), "end": keep[-1]["end"].isoformat()} if keep else {"status": "UNAVAILABLE", "reason": "window_outside_fiscal_calendar"}


def _substatus_band(target: dict) -> dict:
    name = _value(target, "ey_accountsegmentsubstatusidname").casefold()
    if not name:
        return {"status": "UNAVAILABLE", "members": set(), "note": "target account sub-status name unavailable; band filter skipped"}
    if name in {"premier", "strategic", "focus"}:
        return {"status": "MATCHED", "members": {"premier", "strategic", "focus"}, "note": "Premier/Strategic/Focus band applied"}
    if name == "core":
        return {"status": "MATCHED", "members": {"focus", "core"}, "note": "Focus/Core band applied"}
    return {"status": "UNAVAILABLE", "members": set(), "note": f"unknown sub-status band for {name!r}; band filter skipped"}


def _in_substatus_band(row: dict, band: dict) -> bool:
    members = band.get("members") or set()
    if not members:
        return True
    return _value(row, "ey_accountsegmentsubstatusidname").casefold() in members


def _is_global_ultimate_like(row: dict) -> bool:
    entity = _value(row, "ey_entitytypecode")
    if entity.isdigit() and entity not in {"100000003", "100000000"}:
        return False
    state = _value(row, "statecode")
    if state and state not in {"0", "active"}:
        return False
    if _value(row, "name").casefold().startswith("do not use"):
        return False
    return not _value(row, "parentaccountid")


def _schema_notes(accounts: list[dict]) -> list[dict]:
    entity_values = {_value(row, "ey_entitytypecode") for row in accounts[:50] if _value(row, "ey_entitytypecode")}
    notes = []
    if entity_values and not all(value.isdigit() for value in entity_values):
        notes.append({"field": "ey_entitytypecode", "status": "RELAXED", "note": "Synthetic/non-numeric entity type values found; numeric Account/Client/Prospect filter not enforced."})
    return notes


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
    saw_data = False
    for col, score in (("ey_countryid", 1.0), ("ey_hqmarketsbusinessunitid", 0.75), ("ey_hqmarketsregionid", 0.5), ("ey_hqareaid", 0.25)):
        av, bv = _value(a, col), _value(b, col)
        saw_data = saw_data or bool(av and bv)
        if av and bv and av == bv:
            return score
    return 0.0 if saw_data else None


def _company_size(a: dict, b: dict) -> float | None:
    av = _float(_value(a, "numberofemployees") or _value(a, "ey_annualrevenue"))
    bv = _float(_value(b, "numberofemployees") or _value(b, "ey_annualrevenue"))
    if not av or not bv or av <= 0 or bv <= 0:
        return None
    return round(1 - min(1.0, abs(math.log10(av) - math.log10(bv)) / 2), 4)


def _jaccard(a: set, b: set) -> float | None:
    if not a or not b:
        return None
    return round(len(a & b) / len(a | b), 4)


def _cosine(a: dict[str, float], b: dict[str, float]) -> float | None:
    keys = set(a) | set(b)
    if not keys or not a or not b:
        return None
    numerator = sum(float(a.get(k, 0.0)) * float(b.get(k, 0.0)) for k in keys)
    denom_a = math.sqrt(sum(float(a.get(k, 0.0)) ** 2 for k in keys))
    denom_b = math.sqrt(sum(float(b.get(k, 0.0)) ** 2 for k in keys))
    if denom_a == 0 or denom_b == 0:
        return None
    return round(numerator / (denom_a * denom_b), 4)


def _excluded(row: dict, reason: str, seed: str) -> dict:
    return {"accountId": _value(row, "accountid"), "displayName": _value(row, "name"), "reason": reason, "seed": seed}


def _public_account(row: dict) -> dict:
    return {
        "accountId": _value(row, "accountid"),
        "displayName": _value(row, "name"),
        "mdmId": _value(row, "ey_mdmid"),
        "duns": _value(row, "ey_dunsnumber"),
        "globalUltimateDuns": _value(row, "ey_gisultimatedunsnumber") or _value(row, "ey_globalultimateduns"),
        "channel": _value(row, "ey_channel"),
        "subStatus": _value(row, "ey_accountsegmentsubstatusidname"),
    }


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
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR", "TOOLFORGE_REFERENCE_DATA_DIR", "EYBCS_REFERENCE_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    for root in list(roots):
        roots.append(root.parent / "d365_ontology_ext" / "csv")
        roots.append(root.parent / "d365_synthetic")
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_synthetic", Path.cwd() / "data" / "d365_ontology_ext" / "csv"])
    return roots
