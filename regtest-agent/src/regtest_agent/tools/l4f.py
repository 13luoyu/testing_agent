"""LLM4Fin step tools (ours/main.py: nlp_process + alg_process, one tool per original step)."""
from __future__ import annotations

from .base import ToolContext, tool

W = "llm4fin"


@tool("l4f.segment", "文档预处理", W, "ours/process_nl_to_sci.py · nl_to_sci", "LLM4Fin",
      "将PDF/文本切分为带编号的规则句(sci)，识别交易市场与品种", ["doc_main"], ["l4f_sci"])
def segment(ctx: ToolContext) -> dict:
    doc = ctx.load("doc_main")
    out = ctx.worker("l4f", "segment", {"path": doc["path"]} if doc["path"].lower().endswith(".pdf") else {"text": doc["text"]})
    ctx.save("l4f_sci", out)
    return {"summary": {"规则句": out["count"], "交易市场": out["setting"].get("market"), "交易品种": out["setting"].get("variety")}}


@tool("l4f.filter", "过滤不可测规则", W, "ours/process_sci_to_sco.py · sequence_classification (mengzi)", "LLM4Fin mengzi_rule_filtering",
      "句分类：0 不可测自然语言 / 1 可测试规则 / 2 领域知识", ["l4f_sci"], ["l4f_sco"])
def filter_rules(ctx: ToolContext, batch_size: int = 8) -> dict:
    sci = ctx.load("l4f_sci")
    out = ctx.worker("l4f", "filter", {"sci": sci["sci"], "batch_size": batch_size})
    ctx.save("l4f_sco", out)
    t = out["types"]
    return {"summary": {"可测试规则": t.get("1", 0), "领域知识": t.get("2", 0), "不可测": t.get("0", 0)}}


@tool("l4f.extract", "规则元素抽取", W, "ours/process_tci_to_tco.py · token_classification_encoder (mengzi)", "LLM4Fin mengzi_rule_element_extraction",
      "按条款合并可测试规则(tci)，序列标注抽取规则元素(tco)", ["l4f_sco"], ["l4f_tco"])
def extract(ctx: ToolContext, batch_size: int = 8) -> dict:
    sco = ctx.load("l4f_sco")
    out = ctx.worker("l4f", "extract", {"sco": sco["sco"], "batch_size": batch_size})
    ctx.save("l4f_tco", out)
    labels = sum(1 for x in out["tco"] for l in x["label"].split() if l.startswith("B-"))
    return {"summary": {"条款": len(out["tci"]), "抽取元素": labels}}


@tool("l4f.assemble", "形式化规则(R1)", W, "ours/process_tco_to_r1.py · to_r1 + add_defines", "LLM4Fin",
      "将规则元素组装为 if-then 形式化规则（结构化需求 R1）", ["l4f_tco", "l4f_sci"], ["l4f_r1"])
def assemble(ctx: ToolContext) -> dict:
    tco, sci = ctx.load("l4f_tco"), ctx.load("l4f_sci")
    out = ctx.worker("l4f", "assemble", {"tco": tco["tco"], "setting": sci["setting"]})
    ctx.save("l4f_r1", out)
    return {"summary": {"R1规则": out["count"]}}


@tool("l4f.consistency", "需求一致性检测", W, "ours/consistency_checking.py · consistency_checking (z3)", "LLM4Fin z3",
      "检测R1规则之间结果相同但约束互斥等冲突", ["l4f_r1"], ["l4f_conflicts"])
def consistency(ctx: ToolContext) -> dict:
    r1 = ctx.load("l4f_r1")
    out = ctx.worker("l4f", "consistency", {"r1": r1["r1"]})
    ctx.save("l4f_conflicts", out)
    return {"summary": {"检测规则": out["checked"], "冲突对": len(out["conflicts"]), "缺少条件被跳过": len(out["skipped"])}}


@tool("l4f.complete", "规则补全(R2)", W, "ours/process_r1_to_r2.py · preprocess + compose_rules_r1_r2", "LLM4Fin",
      "基于分类知识补全隐含要素、合并嵌套规则、数值/时间预处理", ["l4f_r1"], ["l4f_r2"])
def complete(ctx: ToolContext, concretize: bool = False) -> dict:
    r1 = ctx.load("l4f_r1")
    out = ctx.worker("l4f", "complete", {"r1": r1["r1"], "concretize": concretize})
    ctx.save("l4f_r2_state", out.pop("state"))
    ctx.save("l4f_r2", out)
    return {"summary": {"R1": out["r1_count"], "R2": out["count"]}}


@tool("l4f.relate", "关系挖掘(R3)", W, "ours/process_r2_to_r3.py · compose_rules_r2_r3", "LLM4Fin HanLP",
      "结合状态机生成业务场景，挖掘规则间显式/隐式关系", ["l4f_r2"], ["l4f_r3"])
def relate(ctx: ToolContext) -> dict:
    st = ctx.load("l4f_r2_state")
    out = ctx.worker("l4f", "relate", {"state": st})
    ctx.save("l4f_r3_state", out.pop("state"))
    ctx.save("l4f_r3", out)
    return {"summary": {"场景(R3)": out["count"], "显式关系": out["explicit_count"], "隐式关系": out["implicit_count"]}}


@tool("l4f.generate", "生成测试用例", W, "ours/process_r3_to_testcase.py · testcase + generate_dicts (z3)", "LLM4Fin z3",
      "为每个场景求解测试数据并生成正/反例测试用例", ["l4f_r3"], ["tests"])
def generate(ctx: ToolContext) -> dict:
    st = ctx.load("l4f_r3_state")
    out = ctx.worker("l4f", "generate", {"state": st})
    ctx.save("tests", {"workflow": W, "testcases": out["testcases"]})
    pos = sum(1 for g in out["testcases"] for t in g if t.get("结果") in ("成功", "可以"))
    return {"summary": {"用例组": out["groups"], "测试用例": out["count"], "正例": pos, "反例": out["count"] - pos}}


@tool("l4f.knowledge", "领域知识抽取", W, "ours/process_knowledge.py · process_knowledge", "LLM4Fin",
      "从被分类为领域知识(type 2)的句子中抽取术语定义", ["l4f_sco"], ["l4f_knowledge"])
def knowledge(ctx: ToolContext) -> dict:
    sco = ctx.load("l4f_sco")
    out = ctx.worker("l4f", "knowledge", {"sco": sco["sco"]})
    ctx.save("l4f_knowledge", out)
    return {"summary": {"术语定义": len(out["knowledge"]), "待人工处理": len(out["todo"])}}
