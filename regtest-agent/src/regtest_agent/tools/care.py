"""CARE tools — the reuse/interface.py sequence: requirement_generation → scenario_generation →
testcase_align → change_identify → impact_analysis → testcase_update."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from .base import ToolContext, ToolFailed, tool

W = "care"
SYSTEM = "你是一个金融科技领域的专家。给出一条规则，请你抽取其中的规则元素并组合成R规则的形式。如果组合后的R规则存在冲突，则将其分成多条不冲突的R规则。"
FEWSHOT_FILE = "decoder_lora/predict_data/glm4/predict_result_best_lora_model_1734292066_4bit_load_lora_all.json"


@lru_cache(maxsize=1)
def _fewshot() -> list[tuple[str, str, set]]:
    p = Path(get_settings().care_root) / FEWSHOT_FILE
    out = []
    for x in json.loads(p.read_text(encoding="utf-8")):
        text = x["prompt"].split("规则:")[-1].split("<|assistant|>")[0].strip()
        ans = x["answer"].replace("<|user|>", "").strip()
        if "\nthen " in ans and "if " in ans:
            out.append((text, ans, set(text)))
    return out


def _examples(text: str, k: int = 4) -> list[tuple[str, str]]:
    """Nearest GLM4 training pairs by character overlap (deterministic retrieval)."""
    chars = set(text)
    scored = sorted(_fewshot(), key=lambda t: -len(chars & t[2]) / (len(t[2]) ** 0.5 + 1))
    return [(a, b) for a, b, _ in scored[:k]]


def _clean(ans: str) -> str:
    t = ans.strip()
    m = re.search(r"```(?:\w+)?\s*\n(.*?)```", t, re.S)
    t = (m.group(1) if m else t).strip()
    lines = [re.sub(r"\s+", " ", l).strip() for l in t.split("\n")]
    return "\n".join(l for l in lines if l.startswith(("rule ", "if ", "then ", "or relation")))


def _valid(ans: str) -> bool:
    ls = ans.split("\n")
    return bool(ls) and ls[0].startswith("rule ") and any(l.startswith("then ") for l in ls) and \
        all(len(c.split(" ")) >= 3 for l in ls if l.startswith(("if ", "then ")) for c in l.split(" ", 1)[1].split(" and "))


def wrap(text: str, ans: str) -> str:
    return f"[gMASK]<sop><|system|>\n{SYSTEM}<|user|>\n规则:{text}<|assistant|>\n{ans}<|user|>"


def formalize_rules(ctx: ToolContext, fi: list[dict], label: str) -> tuple[dict, dict]:
    """Stand-in for process_fi_to_fo.rule_formalization (GLM4-LoRA weights unavailable):
    same instruction + nearest GLM4 training pairs as few-shot, local model, GLM4 prediction format."""
    exact = {a: b for a, b, _ in _fewshot()}
    stats = {"exact": 0, "llm": 0, "repaired": 0, "fallback": 0}
    preds = {}

    def one(item):
        text = item["text"]
        if text.strip() in exact:
            return text, exact[text.strip()], "exact"
        msgs = [{"role": "system", "content": SYSTEM + "\n输出格式：每条 R 规则以 'rule N' 开头，随后 'if key is value and ...' 与 'then key is value and ...' 各占一行；只输出 R 规则。"}]
        for q, a in _examples(text):
            msgs += [{"role": "user", "content": f"规则:{q}"}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": f"规则:{text}"})
        ans = _clean(ctx.llm.chat(msgs, max_tokens=1500, kind="care.formalize"))
        if _valid(ans):
            return text, ans, "llm"
        msgs += [{"role": "assistant", "content": ans or "(空)"},
                 {"role": "user", "content": "格式不正确：必须是 rule N / if 三元组 / then 三元组（key is value，以 and 连接）。请重新输出。"}]
        ans = _clean(ctx.llm.chat(msgs, max_tokens=1500, kind="care.formalize"))
        if _valid(ans):
            return text, ans, "repaired"
        return text, "rule 1\nif 操作 is 申报\nthen 结果 is 成功", "fallback"

    for r in ctx.llm_map(one, fi, label):
        if isinstance(r, Exception):
            raise ToolFailed(f"规则形式化失败：{r}")
        text, ans, how = r
        preds[text] = wrap(text, ans)
        stats[how] += 1
    return preds, stats


def _requirements(ctx: ToolContext, role: str) -> dict:
    doc = ctx.load(f"doc_{role}")
    prep = ctx.worker("care", "prepare", {"path": doc["path"]} if doc["path"].lower().endswith(".pdf") else {"text": doc["text"]})
    preds, stats = formalize_rules(ctx, prep["fi"], f"{'原' if role == 'old' else '新'}规则形式化")
    ctx.worker("care", "remember", {"predictions": preds})
    fo = [dict(f, prediction=preds[f["text"]]) for f in prep["fi"]]
    fin = ctx.worker("care", "finish", {"fo": fo})
    sc = ctx.worker("care", "scenarios", {"requirements": fin["requirements"], "sco": prep["sco"], "market_variety": prep["market_variety"]})
    out = {"rules": fin["rules"], "requirements": fin["requirements"], "r1": fin["r1"], "scenarios": sc["scenarios"],
           "sco": prep["sco"], "market_variety": prep["market_variety"], "predictions": preds, "formalize": stats,
           "sci_count": prep["sci_count"]}
    ctx.save(f"care_{role}", out)
    return out


def _n(x) -> int:
    return len(x["rules"]) if isinstance(x, dict) and "rules" in x else len(x or [])


@tool("care.requirements_old", "原规则需求与场景生成", W, "reuse/interface.py · requirement_generation + scenario_generation", "CARE (+local-llm formalization)",
      "原规则：nl_to_sci→规则筛选(mengzi)→R规则形式化→to_r→R1→R2→R3 场景", ["doc_old"], ["care_old"])
def requirements_old(ctx: ToolContext) -> dict:
    o = _requirements(ctx, "old")
    return {"summary": {"规则": len(o["rules"]), "需求(R1)": _n(o["requirements"]), "场景(R3)": _n(o["scenarios"]), "形式化": o["formalize"]}}


@tool("care.requirements_new", "新规则需求与场景生成", W, "reuse/interface.py · requirement_generation + scenario_generation", "CARE (+local-llm formalization)",
      "新规则：同上流程生成需求与场景", ["doc_new"], ["care_new"])
def requirements_new(ctx: ToolContext) -> dict:
    o = _requirements(ctx, "new")
    return {"summary": {"规则": len(o["rules"]), "需求(R1)": _n(o["requirements"]), "场景(R3)": _n(o["scenarios"]), "形式化": o["formalize"]}}


@tool("care.align", "测试用例对齐", W, "reuse/interface.py · testcase_align (relation_mining)", "CARE",
      "把原测试用例与原规则场景对齐，得到 规则→测试用例 的追溯关系", ["care_old", "tests_old"], ["care_relation"])
def align(ctx: ToolContext) -> dict:
    old, tests = ctx.load("care_old"), ctx.load("tests_old")
    out = ctx.worker("care", "align", {"scenarios": old["scenarios"], "testcases": tests["testcases"]})
    rel = out["relation"]
    linked = {t for v in rel.values() for t in v}
    total = sum(len(g) for g in tests["testcases"])
    ctx.save("care_relation", rel)
    return {"summary": {"关联规则": len(rel), "被关联用例": len(linked), "原用例": total, "未关联用例": total - len(linked)}}


@tool("care.diff", "变更规则识别", W, "reuse/interface.py · change_identify", "CARE",
      "比较新旧规则对应的 R3 约束/结果，识别删除(含修改)与新增的规则", ["care_old", "care_new"], ["care_diff"])
def diff(ctx: ToolContext) -> dict:
    old, new = ctx.load("care_old"), ctx.load("care_new")
    out = ctx.worker("care", "diff", {"old_texts": old["rules"], "new_texts": new["rules"],
                                      "old_scenarios": old["scenarios"], "new_scenarios": new["scenarios"]})
    del_ids = {r["id"] for r in out["to_delete_rules"]}
    add_ids = {r["id"] for r in out["to_add_rules"]}
    modified = sorted(del_ids & add_ids)
    out["modified"] = modified
    ctx.save("care_diff", out)
    return {"summary": {"删除/修改(旧)": len(out["to_delete_rules"]), "新增/修改(新)": len(out["to_add_rules"]), "同编号修改": len(modified)}}


@tool("care.impact", "变更影响分析", W, "reuse/interface.py · impact_analysis (generate_linked_scenario)", "CARE",
      "沿场景链找出受删除规则影响的业务场景与测试用例", ["care_old", "care_diff", "care_relation"], ["care_impact"])
def impact(ctx: ToolContext) -> dict:
    old, d, rel = ctx.load("care_old"), ctx.load("care_diff"), ctx.load("care_relation")
    out = ctx.worker("care", "impact", {"old_scenarios": old["scenarios"], "to_delete_rules": d["to_delete_rules"], "old_relation": rel})
    ctx.save("care_impact", out)
    return {"summary": {"受影响场景": len(out["to_delete_scenarios"]), "受影响用例": len(out["to_delete_testcases"])}}


@tool("care.update", "测试用例更新", W, "reuse/interface.py · testcase_update", "CARE z3",
      "删除失效用例、按新规则重映射可复用用例编号、为新增规则生成新用例", ["care_new", "care_diff", "care_relation", "tests_old"], ["tests", "care_update"])
def update(ctx: ToolContext) -> dict:
    new, d, rel, tests = ctx.load("care_new"), ctx.load("care_diff"), ctx.load("care_relation"), ctx.load("tests_old")
    out = ctx.worker("care", "update", {
        "new_texts": new["rules"], "new_scenarios": new["scenarios"], "to_delete_rules": d["to_delete_rules"],
        "to_add_rules": d["to_add_rules"], "old_relation": rel, "old_testcases": tests["testcases"], "new_map": d["new_map"],
        "new_sco": new["sco"], "new_market_variety": new["market_variety"], "predictions": new["predictions"]})
    reused = out["reused"]
    remapped = sum(1 for k, v in reused.items() if k != v)
    total = sum(len(g) for g in out["testcases"])
    added = total - len(reused)
    ctx.save("care_update", {"reused": reused, "deleted": out["deleted"], "renumbered": out.get("renumbered", [])})
    ctx.save("tests", {"workflow": W, "testcases": out["testcases"]})
    return {"summary": {"更新后用例": total, "直接复用": len(reused) - remapped, "重映射复用": remapped, "删除": len(out["deleted"]), "新生成": added,
                        "新用例编号冲突重编号": len(out.get("renumbered", []))}}
