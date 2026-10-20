"""Verification: deterministic traceability / coverage checks plus a local-LLM judge on samples
(evidence quotes must exist in the source rule text, otherwise the verdict is 'uncertain')."""
from __future__ import annotations

import random
import re

from ..tools.base import ToolContext
from .. import views

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "faithful": {"type": "string", "enum": ["yes", "no", "uncertain"]},
        "missing": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 4},
        "evidence": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 3},
        "tests_consistent": {"type": "string", "enum": ["yes", "no", "uncertain"]},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["faithful", "missing", "evidence", "tests_consistent", "reason"],
}
JUDGE_SYS = ("你是测试需求审查员。给定一条原始规则、由工具生成的若干条形式化需求（[编号] if 条件 then 结果）和测试用例"
             "（每条用例标注了“对应需求”），判断：\n"
             "1) faithful：这些形式化需求是否忠实表达了原规则的条件与结果（不能编造原文没有的内容；一条规则拆成多条需求是正常的）；\n"
             "2) missing：原规则中被遗漏的关键要素（没有则为空）；\n"
             "3) evidence：支撑判断的原文片段，必须逐字摘自原始规则；\n"
             "4) tests_consistent：每条用例的预期结果是否与其“对应需求”一致（满足条件→成功，违反条件→不成功）。\n"
             "只根据给定内容判断，不确定时回答 uncertain。")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def deterministic(ctx: ToolContext, workflow: str) -> list[dict]:
    tr = views.trace(ctx.store, ctx.run_id, full=True)
    checks = []
    tests = [n for n in tr["nodes"] if n["type"] == "testcase" and n.get("status") != "deleted"]
    rules = [n for n in tr["nodes"] if n["type"] == "rule" and not n.get("virtual")]
    parents = {}
    for e in tr["edges"]:
        parents.setdefault(e["target"], set()).add(e["source"])
    checks.append({"name": "生成测试用例", "ok": len(tests) > 0, "level": "error", "detail": f"{len(tests)} 条"})
    if not tests:
        return checks
    orphan = [t["id"] for t in tests if not parents.get(t["id"])]
    virtual = {n["id"] for n in tr["nodes"] if n.get("virtual")}
    out_scope = sum(1 for t in tests if parents.get(t["id"]) and parents[t["id"]] <= virtual)
    checks.append({"name": "用例可追溯到场景/需求", "ok": not orphan, "level": "warn" if workflow == "care" else "error",
                   "detail": f"{len(tests) - len(orphan)}/{len(tests)} 可追溯" + (f"（其中 {out_scope} 条为范围外规则的原样复用）" if out_scope else "")
                             + (f"，未关联示例 {orphan[:3]}" if orphan else "")})
    node_type = {n["id"]: n["type"] for n in tr["nodes"]}
    children = {}
    for e in tr["edges"]:
        children.setdefault(e["source"], []).append(e["target"])

    def has_test(nid, seen=None):
        seen = seen or set()
        for c in children.get(nid, []):
            if c in seen:
                continue
            seen.add(c)
            if node_type.get(c) == "testcase" or has_test(c, seen):
                return True
        return False

    active_rules = [r for r in rules if r.get("status") not in ("deleted", "discarded", "unformalized")]
    covered = [r for r in active_rules if has_test(r["id"])]
    ratio = len(covered) / max(1, len(active_rules))
    checks.append({"name": "规则覆盖率", "ok": ratio >= 0.6, "level": "warn", "detail": f"{len(covered)}/{len(active_rules)} 条有效规则有测试用例（{ratio:.0%}）"})
    discarded = [r for r in rules if r.get("status") == "discarded"]
    if discarded:
        checks.append({"name": "判定为不可测而丢弃", "ok": True, "level": "info",
                       "detail": f"{len(discarded)} 条（原因见「规则·需求」页，HITL 时可人工复核）"})
    unformal = [r["label"] for r in rules if r.get("status") == "unformalized"]
    if unformal:
        checks.append({"name": "形式化失败而丢弃", "ok": True, "level": "info",
                       "detail": f"{len(unformal)} 条（Generate-Verify-Repair 达到修复上限仍未通过校验）：{'、'.join(unformal[:8])}"})
    status_of = {n["id"]: n.get("status") for n in tr["nodes"]}
    reqs = [n for n in tr["nodes"] if n["type"] == "requirement" and n.get("side") != "old"
            and any(status_of.get(p) not in ("discarded", "unformalized", "deleted") for p in parents.get(n["id"], {None}))]
    no_scn = [q["label"] for q in reqs if not any(node_type.get(c) == "scenario" for c in children.get(q["id"], []))]
    if reqs:
        checks.append({"name": "需求→场景覆盖", "ok": len(no_scn) <= 0.2 * len(reqs), "level": "warn",
                       "detail": f"{len(reqs) - len(no_scn)}/{len(reqs)} 条需求派生了场景" +
                                 (f"；未派生：{'、'.join(no_scn[:8])}{'…' if len(no_scn) > 8 else ''}（可在级联图中查看）" if no_scn else "")})
    pos = sum(1 for t in tests if str(t.get("expected", "")) in ("成功", "可以", "Success", "success"))
    checks.append({"name": "正反例均衡", "ok": 0 < pos < len(tests), "level": "warn", "detail": f"正例 {pos} / 反例 {len(tests) - pos}"})
    ids = [tc.get("testid") for tc in views.tests_flat(ctx.store, ctx.run_id)]  # raw list: graph nodes are already de-duplicated
    dup = len(ids) - len(set(ids))
    checks.append({"name": "用例编号唯一", "ok": dup == 0, "level": "warn", "detail": f"重复 {dup}"})
    if workflow == "care":
        upd = ctx.load("care_update", {}) or {}
        old_total = sum(len(g) for g in (ctx.load("tests_old", {}) or {}).get("testcases", []))
        acc = len(upd.get("reused", {})) + len(upd.get("deleted", []))
        checks.append({"name": "原用例去向可核对", "ok": acc == old_total, "level": "error",
                       "detail": f"复用 {len(upd.get('reused', {}))} + 删除 {len(upd.get('deleted', []))} = {acc} / 原用例 {old_total}"})
    return checks


def judge(ctx: ToolContext, workflow: str, n: int) -> list[dict]:
    """Local LLM review of n sampled rule→requirement→tests chains (seeded, reproducible)."""
    samples = views.samples(ctx.store, ctx.run_id, workflow)
    if not samples:
        return []
    rnd = random.Random(ctx.run_id)
    pick = rnd.sample(samples, min(n, len(samples)))

    def one(s):
        user = f"原始规则：{s['rule'][:1500]}\n\n形式化需求：\n{s['requirement'][:2400]}\n\n测试用例（节选）：\n" + \
               "\n".join(str(t) for t in s["tests"][:9])
        out = ctx.llm.json([{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}], JUDGE_SCHEMA,
                           max_tokens=500, kind="verify.judge")
        ev_ok = [e for e in out["evidence"] if _norm(e) and _norm(e) in _norm(s["rule"])]
        verdict = out["faithful"]
        if verdict != "uncertain" and out["evidence"] and not ev_ok:
            verdict = "uncertain"
        return {"rule_id": s["rule_id"], "faithful": verdict, "tests_consistent": out["tests_consistent"], "missing": out["missing"],
                "evidence": ev_ok, "reason": out["reason"]}

    res = ctx.llm_map(one, pick, "抽检")
    return [r if isinstance(r, dict) else {"rule_id": p["rule_id"], "faithful": "uncertain", "tests_consistent": "uncertain",
                                           "missing": [], "evidence": [], "reason": f"判定失败：{r}"} for r, p in zip(res, pick)]


def verdict(checks: list[dict], reviews: list[dict]) -> str:
    if any(not c["ok"] and c["level"] == "error" for c in checks):
        return "fail"
    bad = sum(r["faithful"] == "no" or r["tests_consistent"] == "no" for r in reviews)
    if any(not c["ok"] and c["level"] == "warn" for c in checks) or bad:
        return "needs_review"
    return "pass"


def explain(checks: list[dict], reviews: list[dict], v: str) -> str:
    """One line stating exactly what drove the verdict (so the user isn't left guessing)."""
    if v == "fail":
        errs = [c["name"] for c in checks if not c["ok"] and c["level"] == "error"]
        return "未通过：硬性检查未达标 — " + "、".join(errs)
    if v == "pass":
        return f"通过：{len(checks)} 项确定性检查全部达标" + (f"，{len(reviews)} 条抽检均忠实一致" if reviews else "")
    warns = [c["name"] for c in checks if not c["ok"] and c["level"] == "warn"]
    bad = [r["rule_id"] for r in reviews if r["faithful"] == "no" or r["tests_consistent"] == "no"]
    parts = []
    if warns:
        parts.append("提示级检查未达标 — " + "、".join(warns))
    if bad:
        parts.append(f"本地模型抽检认为 {len(bad)} 条存在忠实/一致性问题（{'、'.join(bad[:5])}）")
    return "需人工复核：" + "；".join(parts) if parts else "需人工复核"
