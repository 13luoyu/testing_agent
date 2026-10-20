"""Headless test generation — the LLM4Fin pipeline end-to-end without the HTTP server.

    python -m regtest_agent.generate <rule.pdf|txt> [--out FILE] [--minimize] [--report FILE]

Drives the same audited worker steps the agent uses (segment → filter → extract →
assemble → consistency → complete → relate → generate), optionally applies pairwise
minimization, and writes a provenance-stamped deliverable. Useful for batch runs,
CI, and regenerating experiment baselines without a browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from .config import get_settings
from .workers.client import Pool


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(path: str, do_minimize: bool = False, provenance: dict | None = None,
             emit=print) -> dict:
    """Run the full LLM4Fin pipeline on one document; return a deliverable dict."""
    p = Path(path)
    pool = Pool(get_settings())
    w = pool["l4f"]
    t0 = time.time()
    steps: list[dict] = []

    def run(op, args, label):
        t = time.time()
        out = w.call(op, args)
        dt = round(time.time() - t, 2)
        steps.append({"op": op, "seconds": dt})
        emit(f"  [{op}] {dt}s")
        return out

    is_pdf = p.suffix.lower() == ".pdf"
    seg = run("segment", {"path": str(p)} if is_pdf else {"text": p.read_text(encoding="utf-8")}, "segment")
    emit(f"    规则句 {seg['count']} · {seg['setting']}")
    flt = run("filter", {"sci": seg["sci"]}, "filter")
    emit(f"    可测试 {flt['types'].get('1', 0)} · 领域知识 {flt['types'].get('2', 0)} · 不可测 {flt['types'].get('0', 0)}")
    ext = run("extract", {"sco": flt["sco"]}, "extract")
    asm = run("assemble", {"tco": ext["tco"], "setting": seg["setting"]}, "assemble")
    con = run("consistency", {"r1": asm["r1"]}, "consistency")
    comp = run("complete", {"r1": asm["r1"]}, "complete")
    rel = run("relate", {"state": comp["state"]}, "relate")
    gen = run("generate", {"state": rel["state"]}, "generate")
    testcases = gen["testcases"]
    flat = [tc for g in testcases for tc in g]
    emit(f"    场景 {rel['count']} · 用例 {gen['count']}（正 {sum(1 for tc in flat if tc.get('结果') in ('成功', '可以'))}）")

    minimize_info = None
    if do_minimize:
        from .minimize import minimize as _min
        res = _min(testcases)
        testcases = res["testcases"]
        minimize_info = {k: res[k] for k in ("before", "after", "reduction", "groups_reduced", "examples")}
        flat = [tc for g in testcases for tc in g]
        emit(f"  [minimize] {res['before']} → {res['after']} 条（降 {res['reduction']:.0%}，精简 {res['groups_reduced']} 组）")

    stats = {"rule_sentences": seg["count"], "testable_rules": flt["types"].get("1", 0),
             "clauses": len(ext["tci"]), "requirements_r1": asm["count"], "requirements_r2": comp["count"],
             "scenarios": rel["count"], "conflicts": len(con["conflicts"]), "testcases": len(flat),
             "positive": sum(1 for tc in flat if tc.get("结果") in ("成功", "可以")),
             "negative": sum(1 for tc in flat if tc.get("结果") not in ("成功", "可以"))}
    pool.close()
    return {
        "generated_by": "regtest-agent v2 · LLM4Fin workflow (mengzi rule filtering / element extraction + z3 testcase synthesis)",
        "backend": "mengzi + HanLP + z3 (deterministic; no LLM fallback)",
        "source_provenance": {**(provenance or {}), "file": p.name, "sha256": _sha256(p),
                              "market": seg["setting"].get("market"), "variety": seg["setting"].get("variety")},
        "stats": stats, "steps": steps, "seconds": round(time.time() - t0, 1),
        "minimize": minimize_info, "testcases": testcases,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="regtest_agent.generate", description="Headless LLM4Fin test generation")
    ap.add_argument("doc", help="rule document (.pdf/.txt/.md/.docx)")
    ap.add_argument("--out", default=None, help="output JSON path (default: <doc>_testcases.json)")
    ap.add_argument("--minimize", action="store_true", help="apply pairwise test minimization")
    ap.add_argument("--report", default=None, help="also write an HTML quality report to this path")
    ap.add_argument("--title", default="", help="document title for provenance")
    ap.add_argument("--official-url", default="", help="official source URL for provenance")
    ap.add_argument("--effective-date", default="", help="effective date for provenance")
    a = ap.parse_args()

    prov = {k: v for k, v in {"title": a.title, "official_url": a.official_url,
                              "effective_date": a.effective_date}.items() if v}
    print(f"生成测试用例：{a.doc}")
    deliverable = generate(a.doc, do_minimize=a.minimize, provenance=prov)
    out = Path(a.out) if a.out else Path(a.doc).with_name(Path(a.doc).stem + "_testcases.json")
    out.write_text(json.dumps(deliverable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {deliverable['stats']['testcases']} 条用例 → {out}  （{deliverable['seconds']}s）")

    if a.report:
        from .report import write_report
        rp = write_report(deliverable, Path(a.report))
        print(f"✓ 质量报告 → {rp}")


if __name__ == "__main__":
    main()
