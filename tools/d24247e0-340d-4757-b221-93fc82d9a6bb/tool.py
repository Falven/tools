__all__ = ["relationship_whitespace"]

import csv
import os
from pathlib import Path
from typing import Any


FRAMEWORK_AGREEMENT_CODE = "100000004"
OPEN_STATUS_CODES = {"0", "open", "active"}


def relationship_whitespace(account: str, mode: str = "A", play: str = "", lens_relationships: list[dict] | None = None) -> dict:
    """Find structural relationship gaps without inventing missing LENS facts."""
    mode = mode.upper()
    if mode not in {"A", "B"}:
        raise ValueError("mode must be A or B")
    try:
        accounts = _read_csv_table("account")
        opportunities = _read_csv_table("opportunity")
        products = _read_csv_table("opportunityproduct")
        leads = _read_csv_table("lead")
        contacts = _read_csv_table("contact")
        external = _read_csv_table("ey_externalinvolvedparties")
    except RuntimeError as e:
        lens_summary = _lens_summary(lens_relationships or [])
        return {
            "mode": mode,
            "play": play or None,
            "resolvedAccount": None,
            "verdict": "EY_VALIDATE" if mode == "A" else None,
            "sourceCoverage": {"LENS": {"status": lens_summary["status"], "note": lens_summary.get("reason", "caller supplied lens_relationships")}, "CRM": {"status": "UNAVAILABLE", "reason": str(e)}},
            "relationshipSummary": lens_summary,
            "crmCoverage": {"status": "UNAVAILABLE", "reason": str(e)},
            "relationshipGaps": [{"type": "crm_unavailable", "reason": str(e)}],
            "validation": [{"id": "C2", "status": lens_summary["status"], "note": "Relationship state comes only from LENS when supplied."}, {"id": "C4", "status": "UNAVAILABLE", "note": "CRM buyer-role source unavailable"}, {"id": "C12", "status": "PASS", "note": "No invented contacts, buyers, or owners."}],
            "source_material": "crm-copilot-skills-sandbox/relationship-whitespace/SKILL.md",
        }
    resolved = _resolve_account(accounts, account)
    if resolved is None:
        return {"resolvedAccount": None, "validation": [{"id": "C1", "status": "FAIL", "note": "target_not_found"}]}

    account_ids = _corporate_tree_account_ids(accounts, resolved)
    open_opps = _open_opportunities(opportunities, products, account_ids, play)
    open_leads = _open_leads(leads, account_ids)
    party_summary = _buyer_party_summary(external, contacts, open_opps, open_leads)
    lens_summary = _lens_summary(lens_relationships or [])
    verdict = _mode_a_verdict(lens_summary, party_summary) if mode == "A" else None
    return {
        "mode": mode,
        "play": play or None,
        "resolvedAccount": _public_account(resolved, account_ids),
        "verdict": verdict,
        "sourceCoverage": {
            "LENS": {"status": lens_summary["status"], "note": lens_summary.get("reason", "caller supplied lens_relationships"), "rows": lens_summary.get("relationshipRows", 0)},
            "CRM": {"status": "MATCHED", "openOpportunityCount": len(open_opps), "openLeadCount": len(open_leads), "externalPartyRows": party_summary["externalPartyRows"]},
        },
        "relationshipSummary": lens_summary,
        "crmCoverage": party_summary,
        "relationshipGaps": _gaps(mode, open_opps, open_leads, party_summary, lens_summary),
        "validation": [
            {"id": "C1", "status": "PASS", "note": f"Mode {mode} selected; Mode A remains narrow."},
            {"id": "C2", "status": "PASS" if lens_summary["status"] == "MATCHED" else "UNAVAILABLE", "note": "Relationship state comes only from supplied LENS rows."},
            {"id": "C4", "status": "PASS", "note": "CRM buyer-role route uses ey_externalinvolvedparties."},
            {"id": "C6", "status": "PASS", "note": "No lensBBFopIds or noTouchpoint filter used."},
            {"id": "C12", "status": "PASS", "note": "No invented contacts, buyers, or owners."},
        ],
        "source_material": "crm-copilot-skills-sandbox/relationship-whitespace/SKILL.md",
    }


def _open_opportunities(opps: list[dict], products: list[dict], account_ids: list[str], play: str) -> list[dict]:
    product_opp_ids = None
    if play:
        folded = play.casefold()
        product_opp_ids = {_value(row, "opportunityid") for row in products if folded in (_value(row, "ey_solutionidname") + " " + _value(row, "ey_buyerbasedfieldofplayidname") + " " + _value(row, "ey_servicelineidname")).casefold()}
    out = []
    for row in opps:
        account_id = _value(row, "ey_clientparentaccountid") or _value(row, "accountid")
        if account_id not in account_ids or _value(row, "ey_statuscode").casefold() not in OPEN_STATUS_CODES:
            continue
        if _value(row, "ey_opportunitytypecode") == FRAMEWORK_AGREEMENT_CODE:
            continue
        if product_opp_ids is not None and _value(row, "opportunityid") not in product_opp_ids:
            continue
        out.append(row)
    return out


def _open_leads(leads: list[dict], account_ids: list[str]) -> list[dict]:
    return [row for row in leads if (_value(row, "ey_clientparentaccountid") or _value(row, "accountid")) in account_ids and _value(row, "statecode").casefold() in OPEN_STATUS_CODES]


def _buyer_party_summary(external: list[dict], contacts: list[dict], open_opps: list[dict], open_leads: list[dict]) -> dict[str, Any]:
    opp_ids = {_value(row, "opportunityid") for row in open_opps}
    lead_ids = {_value(row, "leadid") for row in open_leads}
    ext = [row for row in external if _value(row, "ey_opportunityid") in opp_ids or _value(row, "ey_leadid") in lead_ids]
    contacts_by_id = {_value(row, "contactid"): row for row in contacts}
    named_ids = sorted({_value(row, "ey_partyid") for row in ext if _value(row, "ey_partyid")})
    return {
        "externalPartyRows": len(ext),
        "openOpportunities": len(open_opps),
        "openOpportunitiesWithNamedParty": len({_value(row, "ey_opportunityid") for row in ext if _value(row, "ey_opportunityid") in opp_ids}),
        "openLeads": len(open_leads),
        "openLeadsWithPrimaryContact": len([row for row in open_leads if _value(row, "ey_primaryclientcontact")]),
        "namedContacts": [{"contactId": cid, "name": _value(contacts_by_id.get(cid, {}), "fullname"), "email": _value(contacts_by_id.get(cid, {}), "emailaddress1").lower(), "jobTitle": _value(contacts_by_id.get(cid, {}), "jobtitle")} for cid in named_ids],
    }


def _lens_summary(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"status": "UNAVAILABLE", "reason": "LENS relationship rows not supplied or adapter not wired."}
    trusted = [r for r in rows if _value(r, "currentRelationship").casefold() in {"trusted", "professional trusted advisor", "personal trusted advisor", "5", "6", "7"}]
    fading = [r for r in rows if _value(r, "trend").casefold() == "fading"]
    unowned = [r for r in trusted if not (_value(r, "PrimaryRmOwner") or _value(r, "primaryRmOwner") or _value(r, "relationshipOwner"))]
    return {"status": "MATCHED", "relationshipRows": len(rows), "trustedPlusCount": len(trusted), "fadingCount": len(fading), "unownedSeniorCount": len(unowned)}


def _mode_a_verdict(lens: dict, party: dict) -> str:
    if lens["status"] != "MATCHED":
        return "EY_VALIDATE"
    if int(lens.get("trustedPlusCount", 0)) == 0:
        return "BLOCKED"
    if int(lens.get("unownedSeniorCount", 0)) > 0 or int(lens.get("fadingCount", 0)) > 0:
        return "BUILD"
    if party["openOpportunities"] and not party["openOpportunitiesWithNamedParty"]:
        return "BUILD"
    return "PURSUE"


def _gaps(mode: str, open_opps: list[dict], open_leads: list[dict], party: dict, lens: dict) -> list[dict]:
    gaps = []
    if party["openOpportunities"] and not party["openOpportunitiesWithNamedParty"]:
        gaps.append({"type": "opportunity_without_named_party", "count": party["openOpportunities"]})
    if lens["status"] == "UNAVAILABLE":
        gaps.append({"type": "lens_unavailable", "reason": lens["reason"]})
    elif lens.get("trustedPlusCount", 0) == 0:
        gaps.append({"type": "no_senior_lens_access"})
    if mode == "B" and party["openLeads"] and not party["openLeadsWithPrimaryContact"]:
        gaps.append({"type": "open_leads_without_primary_contact", "count": party["openLeads"]})
    return gaps


def _resolve_account(rows: list[dict], identifier: str) -> dict | None:
    ident = identifier.strip().casefold()
    for col in ("accountid", "ey_mdmid", "ey_dunsnumber", "ey_gisultimatedunsnumber", "ey_globalultimateduns", "name"):
        matches = [row for row in rows if _value(row, col).casefold() == ident]
        if len(matches) == 1:
            return matches[0]
    matches = [row for row in rows if ident in _value(row, "name").casefold()]
    return matches[0] if len(matches) == 1 else None


def _corporate_tree_account_ids(accounts: list[dict], row: dict) -> list[str]:
    duns = _value(row, "ey_dunsnumber")
    uduns = _value(row, "ey_gisultimatedunsnumber") or _value(row, "ey_globalultimateduns") or duns
    ids = {_value(row, "accountid")}
    for account in accounts:
        if uduns and (_value(account, "ey_gisultimatedunsnumber") == uduns or _value(account, "ey_globalultimateduns") == uduns or _value(account, "ey_dunsnumber") == duns):
            ids.add(_value(account, "accountid"))
    return sorted(i for i in ids if i)


def _public_account(row: dict, account_ids: list[str]) -> dict:
    return {"accountId": _value(row, "accountid"), "displayName": _value(row, "name"), "duns": _value(row, "ey_dunsnumber"), "globalUltimateDuns": _value(row, "ey_gisultimatedunsnumber") or _value(row, "ey_globalultimateduns"), "channel": _value(row, "ey_channel"), "corporateTreeAccountCount": len(account_ids)}


def _value(row: dict, key: str) -> str:
    value = row.get(key, "")
    return "" if value is None or str(value).strip().casefold() in {"", "nan", "none", "null"} else str(value).strip()


def _read_csv_table(name: str) -> list[dict[str, str]]:
    for root in _data_roots():
        path = root / f"{name}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
    raise RuntimeError(f"UNAVAILABLE: table {name!r} not found. Set TOOLFORGE_DATA_DIR or mount CRM data.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_synthetic"])
    return roots
