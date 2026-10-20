"""Pairwise (2-wise) test minimization.

A rule can fan out to a cartesian product of enum values (e.g. 32 near-identical cases).
This selects a minimal SUBSET of the already-generated cases that still covers every
observed value-pair and keeps both 成功/不成功 outcomes — so no combination is invented
and every kept case keeps its original evidence. The full suite stays canonical; the
minimized suite is an additive, auditable view.
"""
from __future__ import annotations

from itertools import combinations

SKIP = {"testid", "rule", "测试关注点", "结果"}  # ids/outcome are not interaction factors
RESULT = "结果"


def _factors(group: list[dict]) -> list[str]:
    """Keys whose value varies across the group (the dimensions that cause the fan-out)."""
    keys = {k for tc in group for k in tc if k not in SKIP}
    return sorted(k for k in keys if len({tc.get(k) for tc in group}) > 1)


def _pairs(tc: dict, factors: list[str]) -> set:
    """Value-pairs (and singletons, so a 1-factor group still gets covered) of one case."""
    vals = [(k, tc.get(k)) for k in factors]
    out = {(a, b) for a, b in combinations(vals, 2)}
    out |= {(v,) for v in vals}  # singletons cover the degenerate single-factor case
    return out


def minimize_group(group: list[dict], min_size: int = 4) -> tuple[list[dict], dict]:
    """Greedy set cover over observed value-pairs, preserving both result classes.

    Returns (kept cases in original order, info). Groups at/below min_size are kept whole."""
    if len(group) <= min_size:
        return group, {"kept": len(group), "total": len(group), "reason": "small"}
    factors = _factors(group)
    if not factors:
        return group[:1], {"kept": 1, "total": len(group), "reason": "identical"}
    need = set().union(*(_pairs(tc, factors) for tc in group))
    chosen, covered = [], set()
    pool = list(group)
    while covered < need and pool:
        best = max(pool, key=lambda tc: len(_pairs(tc, factors) - covered))
        gain = _pairs(best, factors) - covered
        if not gain:
            break
        chosen.append(best)
        covered |= _pairs(best, factors)
        pool.remove(best)
    # keep at least one case of each observed 结果 (成功 and 不成功 both matter)
    picked = {id(tc) for tc in chosen}
    for res in {tc.get(RESULT) for tc in group}:
        if not any(tc.get(RESULT) == res for tc in chosen):
            extra = next((tc for tc in group if tc.get(RESULT) == res), None)
            if extra is not None and id(extra) not in picked:
                chosen.append(extra)
                picked.add(id(extra))
    kept = [tc for tc in group if id(tc) in picked]  # original order
    return kept, {"kept": len(kept), "total": len(group), "factors": factors, "reason": "pairwise"}


def minimize(testcases: list[list[dict]], min_size: int = 4) -> dict:
    """Minimize every group. Returns the reduced suite plus coverage stats."""
    out, groups_info = [], []
    total_before = total_after = 0
    for g in testcases:
        kept, info = minimize_group(g, min_size)
        out.append(kept)
        total_before += len(g)
        total_after += len(kept)
        if info["total"] > info["kept"]:
            groups_info.append({"rule": g[0].get("rule") if g else "", **info})
    reduced = sorted(groups_info, key=lambda x: x["kept"] - x["total"])[:20]
    return {"testcases": out, "before": total_before, "after": total_after,
            "reduction": round(1 - total_after / max(1, total_before), 3),
            "groups_reduced": len(groups_info), "examples": reduced}
