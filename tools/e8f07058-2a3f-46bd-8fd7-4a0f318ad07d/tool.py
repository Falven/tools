__all__ = ["confidence_scoring"]

import csv
import os
from pathlib import Path


def confidence_scoring(factor_scores: dict[str, float], factor_weights: dict[str, float] | None = None, high_threshold: float = 0.75, medium_threshold: float = 0.5) -> dict:
    """Compute deterministic confidence from evidence using supplied or configured weights."""
    try:
        weights, weight_source = _load_weights(factor_weights)
    except (RuntimeError, ValueError) as e:
        return {
            "aggregate": 0.0,
            "level": "Ineligible",
            "appliedFactors": {},
            "missingFactors": [],
            "unknownFactorsIgnored": sorted(str(name) for name in factor_scores),
            "topDrivers": [],
            "topDetractors": [],
            "thresholds": {"high": high_threshold, "medium": medium_threshold},
            "sourceCoverage": {"weights": {"status": "UNAVAILABLE", "reason": str(e)}},
            "validation": [{"id": "CS1", "status": "UNAVAILABLE", "note": "confidence weights unavailable"}],
            "source_material": "crm-copilot-skills-sandbox/confidence-scoring/SKILL.md",
        }
    applied = {}
    missing = []
    weighted_sum = 0.0
    applied_weight = 0.0
    for name, weight in weights.items():
        if name not in factor_scores:
            missing.append(name)
            continue
        score = max(0.0, min(1.0, float(factor_scores[name])))
        applied[name] = score
        weighted_sum += score * float(weight)
        applied_weight += float(weight)
    unknown = [name for name in factor_scores if name not in weights]
    aggregate = 0.0 if applied_weight == 0 else weighted_sum / applied_weight
    if applied_weight == 0:
        level = "Ineligible"
    elif aggregate >= high_threshold:
        level = "High"
    elif aggregate >= medium_threshold:
        level = "Medium"
    else:
        level = "Low"
    if applied.get("channel_eligibility") == 0:
        level = "Ineligible"
    if missing and level == "High":
        level = "Medium"
    return {
        "aggregate": round(aggregate, 3),
        "level": level,
        "appliedFactors": applied,
        "missingFactors": missing,
        "unknownFactorsIgnored": unknown,
        "topDrivers": sorted(applied, key=applied.get, reverse=True)[:3],
        "topDetractors": sorted(applied, key=applied.get)[:3],
        "thresholds": {"high": high_threshold, "medium": medium_threshold},
        "sourceCoverage": {"weights": weight_source},
        "validation": [
            {"id": "CS1", "status": "PASS", "note": "confidence weights loaded"},
            {"id": "CS2", "status": "PASS" if applied else "UNAVAILABLE", "note": "evidence factors applied"},
            {"id": "CS3", "status": "PASS" if not missing else "UNAVAILABLE", "note": "missing factors lower or cap confidence"},
            {"id": "CS4", "status": "PASS" if applied.get("channel_eligibility") != 0 else "FAIL", "note": "channel ineligibility prevents high confidence"},
        ],
        "source_material": "crm-copilot-skills-sandbox/confidence-scoring/SKILL.md",
    }


def _load_weights(factor_weights: dict[str, float] | None) -> tuple[dict[str, float], dict]:
    if factor_weights:
        return {str(k): float(v) for k, v in factor_weights.items()}, {"status": "MATCHED", "source": "caller_supplied"}
    try:
        rows = _read_csv_table("ey_rankingfactor")
    except RuntimeError as e:
        raise RuntimeError(f"UNAVAILABLE: confidence factor weights are required. {e}")
    weights = {}
    for row in rows:
        name = row.get("factor_name") or row.get("name")
        weight = row.get("weight")
        if name and weight is not None:
            weights[str(name)] = float(weight)
    if not weights:
        raise ValueError("ey_rankingfactor did not contain factor_name/name and weight columns.")
    return weights, {"status": "MATCHED", "source": "ey_rankingfactor", "rows": len(weights)}


def _read_csv_table(name: str) -> list[dict[str, str]]:
    for root in _data_roots():
        path = root / f"{name}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
    raise RuntimeError(f"table {name!r} not found. Set TOOLFORGE_DATA_DIR or pass factor_weights.")


def _data_roots() -> list[Path]:
    roots = []
    for env in ("TOOLFORGE_DATA_DIR", "EYBCS_DATA_DIR"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]))
    roots.extend([Path.cwd(), Path.cwd() / "data", Path.cwd() / "data" / "d365_ontology_ext" / "csv"])
    return roots
