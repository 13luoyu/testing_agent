"""RAFT tools. Prompts are RAFT's own files (data/input_prompt/*.md, experiment/exp5/prompt/*.md);
the LLM backend is the local model (N candidates via decoding diversity)."""
from __future__ import annotations

import json
import re
import time

from ..knowledge import (CN, LAYERS, KnowledgeBase, aggregate, clean_symbols, consensus, keymap, parse_bnf,
                         parse_ocl, parse_puml, parse_symbols, raft_assets, render_ocl, render_representation,
                         split_sections)
from ..llm import LLMError, strip_fences
from . import trl as T
from .base import ToolContext, ToolFailed, tool

W = "raft"
_FILES: dict = {}


def files(ctx: ToolContext) -> dict:
    if not _FILES:
        _FILES.update(raft_assets(ctx.llm.settings))
    return _FILES


def _corpus(ctx: ToolContext, limit_chars: int = 12000) -> tuple[str, list]:
    doc = ctx.load("doc_main")
    tests = ctx.load("tests_old", {}) or {}
    flat = [tc for g in tests.get("testcases", []) for tc in g][:20]
    return doc["text"][:limit_chars], flat


def _pack(ctx: ToolContext) -> dict:
    dom = ctx.load("domain")["domain"]
    pack = ctx.load("raft_pack", {}) or KnowledgeBase().get(dom)
    if not pack:
        raise ToolFailed(f"领域 {dom} 没有可用的 RAFT 知识（元模型/需求表示），需要先执行知识工程")
    return pack


# ---------------------------------------------------------------- Phase I --
@tool("raft.meta_model", "构建领域元模型 M", W, "data/input_prompt/meta_model_generation.md · K-consensus purification",
      "local-llm", "N 个候选元模型（PlantUML）→ 语义对齐 → K 多数共识提纯，低共识要素归入 Others", ["doc_main"], ["raft_mm"])
def meta_model(ctx: ToolContext, n: int | None = None, k: int | None = None) -> dict:
    s = ctx.llm.settings
    n, k = n or s.raft_n, k or s.raft_k
    if not (n // 2 + 1 <= k <= n):
        raise ToolFailed(f"K 必须满足 ⌊N/2⌋+1 ≤ K ≤ N（N={n}, K={k}）")
    sys_prompt = files(ctx)["prompts"]["meta_model"]
    docs, tests = _corpus(ctx)
    dom = ctx.load("domain")
    user = "Generate a PlantUML meta model based on the provided regulatory documents and test cases.\n\n"
    user += f"Domain: {dom.get('title') or dom['domain']}\n\nRegulatory Documents:\n{docs}\n\n"
    user += "Test Cases:\n" + (json.dumps(tests, indent=2, ensure_ascii=False) if tests else "(none provided)") + "\n\n"
    temps = (s.raft_temps * 2 * n)[:2 * n]

    def one(t):
        text = ctx.llm.chat([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                            temperature=t, max_tokens=2500, kind="raft.meta_model")
        return {"text": text, "parsed": parse_puml(text), "temperature": t}

    # one local model stands in for RAFT's N LLMs: unparsable candidates are replaced by fresh samples (≤ 2N calls)
    cands, tried = [], 0
    while len(cands) < n and tried < len(temps):
        batch = temps[tried:tried + n - len(cands)]
        tried += len(batch)
        cands += [c for c in ctx.llm_map(one, batch, "候选元模型") if not isinstance(c, Exception) and len(c["parsed"]["entities"]) >= 3]
    if len(cands) < k:
        raise ToolFailed(f"{tried} 次采样中有效候选元模型只有 {len(cands)} 个，少于共识阈值 K={k}")
    merges = _align(ctx, [c["parsed"] for c in cands])
    aligned = [_rename(c["parsed"], merges) for c in cands]
    mm = consensus(aligned, k)
    ctx.save("raft_mm", {"consensus": mm, "candidates": cands, "aligned": aligned, "merges": merges, "n": len(cands), "k": k})
    return {"summary": {"候选": len(cands), "采样": tried, "语义合并": len(merges), "K": k, "保留要素": len(mm["entities"]),
                        "Others": len(mm["others"]["entities"]), "关系": len(mm["relations"])}}


ALIGN_SCHEMA = {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "object", "properties": {
    "canonical": {"type": "string"}, "members": {"type": "array", "items": {"type": "string"}, "minItems": 2}},
    "required": ["canonical", "members"]}}}, "required": ["groups"]}


def _align(ctx: ToolContext, cands: list[dict]) -> dict:
    """Semantic alignment before voting: synonymous leaf elements from different candidates
    (e.g. ExpiryDate / ExpirationDate) are mapped to one canonical name."""
    names = sorted({e for c in cands for e in c["entities"]})
    if len(names) < 2:
        return {}
    try:
        out = ctx.llm.json([{"role": "system", "content": "You align domain meta-model elements produced by different models. Group element names "
                                                          "that denote the same rule element (synonyms, spelling or granularity variants). Only group "
                                                          "names from the list; every group needs at least two members; the canonical name must be one "
                                                          "of the members. Leave distinct concepts ungrouped."},
                            {"role": "user", "content": json.dumps(names)}], ALIGN_SCHEMA, max_tokens=1200, kind="raft.align")
    except LLMError:
        return {}  # voting on exact names only
    merges = {}
    for g in out["groups"]:
        ms = [m for m in g["members"] if m in names]
        canon_ = g["canonical"] if g["canonical"] in ms else (ms[0] if ms else "")
        for m in ms:
            if m != canon_ and m not in merges:
                merges[m] = canon_
    return merges


def _rename(mm: dict, merges: dict) -> dict:
    ren = lambda x: merges.get(x, x)  # noqa: E731
    ents = {}
    for e, layer in mm["entities"].items():
        ents.setdefault(ren(e), layer)
    return {"entities": ents, "relations": sorted({(ren(a), r, ren(b)) for a, r, b in mm["relations"]})}


def _mm_puml(mm: dict) -> str:
    lines = ["@startuml", "class Rule"] + [f"class {x}" for x in LAYERS] + [f"class {e}" for e in mm["entities"]]
    lines += [f"{a} --> {b} : {r}" for a, r, b in mm["relations"]]
    return "\n".join(lines + ["@enduml"])


@tool("raft.representation", "定义需求表示 R 与可测试性约束 T", W,
      "data/input_prompt/testable_requirement_representation_generation.md · union aggregation", "local-llm",
      "基于元模型生成 N 个候选（符号/BNF语法/OCL约束），并集聚合；同时生成中文标签供后处理映射", ["raft_mm"], ["raft_rep"])
def representation(ctx: ToolContext, n: int | None = None) -> dict:
    s = ctx.llm.settings
    n = n or s.raft_n
    mm = ctx.load("raft_mm")["consensus"]
    puml = _mm_puml(mm)
    sys_prompt = files(ctx)["prompts"]["representation"].replace("{}", puml)
    docs, tests = _corpus(ctx, 8000)
    user = "Generate a testable requirement representation based on the provided regulatory documents and test cases.\n\n"
    user += f"Regulatory Documents:\n{docs}\n\nTest Cases:\n" + (json.dumps(tests, indent=2, ensure_ascii=False) if tests else "(none provided)") + "\n\n"
    temps = (s.raft_temps * n)[:n]

    def one(t):
        text = ctx.llm.chat([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                            temperature=t, max_tokens=3500, kind="raft.representation")
        sec = split_sections(text)
        return {"text": text, "temperature": t, "symbols": parse_symbols(sec["symbols"] or text, mm["entities"]) or parse_symbols(text, mm["entities"]),
                "bnf": parse_bnf(sec["syntax"] or text), "ocl": parse_ocl(sec["constraints"] or text)}

    cands = [c for c in ctx.llm_map(one, temps, "候选需求表示") if not isinstance(c, Exception)]
    if not cands:
        raise ToolFailed("没有生成任何有效的需求表示候选")
    rep = aggregate(cands)
    for e, layer in mm["entities"].items():  # every purified element must be expressible
        if all(e not in xs for xs in rep["symbols"].values()):
            rep["symbols"].setdefault(layer, []).append(e)
    rep["symbols"] = clean_symbols(rep["symbols"], set(mm["entities"]) | set(CN) | {x for c in cands for xs in c["symbols"].values() for x in xs})
    for layer, x in (("Operation", "Action"), ("ExpectedResult", "Result")):  # referenced by RAFT's ActionExecutable / ExpectedResultObservable
        if all(x not in xs for xs in rep["symbols"].values()):
            rep["symbols"].setdefault(layer, []).append(x)
    if not rep["ocl"]:
        rep["ocl"] = parse_ocl(files(ctx)["finance"]["representation"])
        rep["ocl_source"] = "RAFT finance artifact (candidates contained no parsable OCL)"
    if not rep["bnf"]:
        rep["bnf"] = parse_bnf(files(ctx)["finance"]["representation"])
    rep["labels"] = _labels(ctx, rep)
    ctx.save("raft_rep", {"representation": rep, "candidates": cands})
    return {"summary": {"候选": len(cands), "领域符号": sum(len(v) for v in rep["symbols"].values()),
                        "语法产生式": len(rep["bnf"]), "OCL约束": len(rep["ocl"])}}


LABEL_SCHEMA = {"type": "object", "properties": {"labels": {"type": "array", "items": {"type": "object", "properties": {
    "symbol": {"type": "string"}, "label": {"type": "string", "maxLength": 12}}, "required": ["symbol", "label"]}}}, "required": ["labels"]}


def _labels(ctx: ToolContext, rep: dict) -> dict:
    """Chinese key per symbol (RAFT post_process keymap convention: Actor->操作主体 ...)."""
    syms = [x for xs in rep["symbols"].values() for x in xs]
    known = {x: CN[x] for x in syms if x in CN}
    todo = [x for x in syms if x not in known]
    if todo:
        out = ctx.llm.json([{"role": "system", "content": "为每个英文领域符号给出简短中文名称（2-6个字），用于测试用例的字段名。"
                                                          f"参考已有约定：{json.dumps(dict(list(CN.items())[:16]), ensure_ascii=False)}"},
                            {"role": "user", "content": json.dumps(todo)}], LABEL_SCHEMA, max_tokens=800, kind="raft.labels")
        for it in out["labels"]:
            if it["symbol"] in todo and it["label"].strip():
                known[it["symbol"]] = it["label"].strip()
    return known


@tool("raft.register", "登记领域知识", W, "knowledge base", "local",
      "把提纯后的元模型 M、聚合的需求表示 R 和可测试性约束 T 存入知识库，供后续同领域任务复用", ["raft_mm", "raft_rep"], ["raft_pack"])
def register(ctx: ToolContext) -> dict:
    dom = ctx.load("domain")
    mm, rep = ctx.load("raft_mm"), ctx.load("raft_rep")
    pack = {"domain": dom["domain"], "title": dom.get("title") or dom["domain"], "source": "raft-built", "workflow": "raft",
            "keywords": dom.get("keywords") or [dom.get("title") or dom["domain"]],
            "meta_model": mm["consensus"], "meta_model_puml": _mm_puml(mm["consensus"]), "representation": rep["representation"],
            "candidates": {f"cand{i + 1}": {"meta_model": c["parsed"], "temperature": c["temperature"]} for i, c in enumerate(mm["candidates"])},
            "provenance": f"RAFT Phase I on run {ctx.run_id}: N={mm['n']} candidates, K={mm['k']} consensus; representation union of {len(rep['candidates'])}",
            "built_from": ctx.load("doc_main")["name"], "built_at": time.time()}
    KnowledgeBase().put(pack)
    ctx.save("raft_pack", pack)
    return {"summary": {"领域": pack["title"], "元模型要素": len(pack["meta_model"]["entities"]),
                        "领域符号": sum(len(v) for v in pack["representation"]["symbols"].values()),
                        "约束": len(pack["representation"]["ocl"])}}


# --------------------------------------------------------------- Phase II --
@tool("raft.segment", "文档预处理", W, "experiment/exp1/document_preprocess.py · read_pdf_to_text2 + read_txt_to_json", "RAFT",
      "按 RAFT main.py 的方式把文档切分为规则句", ["doc_main"], ["raft_rules"])
def segment(ctx: ToolContext, max_rules: int = 400) -> dict:
    doc = ctx.load("doc_main")
    out = ctx.worker("raft", "segment", {"path": doc["path"]} if doc["path"].lower().endswith(".pdf") else {"text": doc["text"]})
    rules = [r for r in out["rules"] if len(r["rule"].strip()) >= 6]
    cut = len(rules) > max_rules
    rules = rules[:max_rules]
    ctx.save("raft_rules", {"rules": rules, "lang": doc["lang"], "truncated": cut})
    return {"summary": {"规则句": len(rules), "语言": doc["lang"], "截断": cut}}


TRANSLATE_SCHEMA = {"type": "object", "properties": {"zh": {"type": "string"}}, "required": ["zh"]}


@tool("raft.translate", "规则翻译为中文", W, "experiment/exp5/translate.py · translator prompt", "local-llm",
      "非中文规则按 RAFT exp5 的翻译提示词译为中文（rule_cn），供下游中文后处理/生成", ["raft_rules"], ["raft_rules"])
def translate(ctx: ToolContext) -> dict:
    data = ctx.load("raft_rules")
    if data["lang"] == "zh":
        return {"summary": {"跳过": "文档已是中文"}}
    sp = files(ctx)["translate_prompt"]

    def one(r):
        return ctx.llm.chat([{"role": "system", "content": sp}, {"role": "user", "content": r["rule"]}], max_tokens=800, kind="raft.translate").strip()

    out = ctx.llm_map(one, data["rules"], "翻译")
    for r, o in zip(data["rules"], out):
        r["rule_cn"] = o if isinstance(o, str) and o else r["rule"]
    ctx.save("raft_rules", data)
    return {"summary": {"翻译规则": sum(isinstance(o, str) for o in out), "失败": sum(isinstance(o, Exception) for o in out)}}


REQ_SCHEMA = {"type": "object", "properties": {"is_requirement": {"type": "boolean"}, "reason": {"type": "string", "maxLength": 120}},
              "required": ["is_requirement", "reason"]}


def _classify_prompt(ctx: ToolContext, dom: dict) -> tuple[str, str]:
    """RAFT exp5 requirement-classification prompt. Its domain examples cover traffic/power; for any other
    domain the same template is instantiated with the domain title and the meta-model elements from Phase I."""
    sp = files(ctx)["classify_prompt_crossdomain"]
    if dom["domain"] in ("traffic", "power"):
        return sp, "exp5 LLM prompt"
    pack = KnowledgeBase().get(dom["domain"]) or {}
    rep = pack.get("representation") or {}
    elems = [rep.get("labels", {}).get(x) or CN.get(x) or x for xs in (rep.get("symbols") or {}).values() for x in xs][:14]
    title = dom.get("title") or dom["domain"]
    sp = sp.replace("是否是软件/硬件需求", f"是否是{title}领域的需求")
    sp = re.sub(r"如自动驾驶系统.*?故障、异常等", f"{title}领域中相关主体、产品或系统应满足的功能、非功能要求，如{'、'.join(elems) or '条件、操作、结果'}等", sp)
    sp = sp.replace("与软硬件功能无关的规则不是需求", f"与{title}领域要求无关的规则不是需求")
    return sp, f"exp5 LLM prompt（领域示例实例化为「{title}」）"


@tool("raft.filter", "可测试规则筛选", W, "experiment/exp1/rule_classify.py (mengzi) · exp5/rule_classify.py (LLM)", "RAFT mengzi / local-llm",
      "金融领域用 mengzi_rule_filtering 判定；其他领域按 RAFT exp5 的需求判定提示词由本地模型判定", ["raft_rules"], ["raft_rules"])
def filter_rules(ctx: ToolContext) -> dict:
    data = ctx.load("raft_rules")
    dom = ctx.load("domain")
    if dom["domain"] == "finance":
        res = ctx.worker("raft", "filter", {"texts": [r["rule_cn"] for r in data["rules"]]})["testable"]
        method = "mengzi_rule_filtering"
    else:
        sp, method = _classify_prompt(ctx, dom)

        def one(r):
            return ctx.llm.json([{"role": "system", "content": sp}, {"role": "user", "content": r["rule_cn"]}], REQ_SCHEMA,
                                max_tokens=200, kind="raft.filter")
        out = ctx.llm_map(one, data["rules"], "需求判定")
        res = [bool(o["is_requirement"]) if isinstance(o, dict) else False for o in out]
        for r, o in zip(data["rules"], out):
            r["filter_reason"] = o["reason"] if isinstance(o, dict) else f"判定失败: {o}"
    for r, ok in zip(data["rules"], res):
        r["testable"] = bool(ok)
    ctx.save("raft_rules", data)
    return {"summary": {"方法": method, "可测试": sum(res), "过滤": len(res) - sum(res)}}


def _requirement_prompt(ctx: ToolContext, pack: dict) -> str:
    rep = pack["representation"]
    dom = pack["domain"]
    if pack.get("trl_prompt"):
        return pack["trl_prompt"]
    if dom == "finance" and pack.get("representation_text"):
        sym, syn = _finance_defs(pack["representation_text"])
    else:
        sym, syn = render_representation(rep)
    tmpl = files(ctx)["prompts"]["requirement"]
    a, b = tmpl.split("{}", 1)
    return a + sym + b.replace("{}", syn, 1) + "\n\n### Annotations\nWhen the rule implies a required pre-operation state or a resulting post-operation state, " \
        "add `Status = <pre-state>` to the if part and `ResultStatus = <post-state>` to the then part; only use states supported by the rule text."


def _finance_defs(text: str) -> tuple[str, str]:
    sec = split_sections(text)
    return sec["symbols"] or text, sec["syntax"] or text


def _check_ctx(pack: dict, rule: dict, doc_text: str = "") -> tuple[set, set, list]:
    rep = pack["representation"]
    syms = {x for xs in rep["symbols"].values() for x in xs} | {"Status", "ResultStatus", "Result", "Constraint"}
    labels = set((rep.get("labels") or {}).values()) | set(CN.values())
    return syms, labels, [rule["rule"], rule.get("rule_cn", ""), T.DOC_MARK + doc_text]


@tool("raft.formalize", "形式化需求生成", W, "data/input_prompt/requirement_generation.md · Generate-Verify-Repair", "local-llm",
      "注入需求表示 R 的提示词逐条生成 TRL；语法/键/取值依据校验失败则带定位诊断修复，最多 3 次，仍失败则丢弃", ["raft_rules"], ["raft_rules"])
def formalize(ctx: ToolContext, max_repairs: int | None = None) -> dict:
    pack = _pack(ctx)
    data = ctx.load("raft_rules")
    sp = _requirement_prompt(ctx, pack)
    max_repairs = ctx.llm.settings.raft_repairs if max_repairs is None else max_repairs
    for r in data["rules"]:
        for k in ("trl", "gvr", "trl_final", "testability", "trl_postprocess", "parse", "testcase", "trl_parsed", "sub_tests"):
            r.pop(k, None)
    todo = [r for r in data["rules"] if r.get("testable")]
    doc_text = ctx.load("doc_main")["text"]

    def one(r):
        msgs = [{"role": "system", "content": sp},
                {"role": "user", "content": f"Generate structured requirements for the following regulatory rule:\n\nRule: {r['rule_cn']}\n\n"}]
        syms, labels, srcs = _check_ctx(pack, r, doc_text)
        history = []
        for attempt in range(max_repairs + 1):
            out = T.normalize(ctx.llm.chat(msgs, max_tokens=1200, kind="raft.formalize"))
            chk = T.check(out, syms, labels, srcs)
            history.append({"trl": out, "errors": chk["errors"], "warnings": chk["warnings"]})
            if chk["ok"]:
                return {"trl": out, "attempts": attempt + 1, "history": history, "status": "ok"}
            msgs = msgs + [{"role": "assistant", "content": out},
                           {"role": "user", "content": "上面的可测试需求存在以下问题，请只修改有问题的部分，保持其余内容不变，然后输出完整的可测试需求：\n- "
                                                       + "\n- ".join(chk["errors"])}]
        return {"trl": "", "attempts": max_repairs + 1, "history": history, "status": "discarded"}

    out = ctx.llm_map(one, todo, "形式化")
    stats = {"ok": 0, "discarded": 0, "error": 0, "repaired": 0}
    for r, o in zip(todo, out):
        if isinstance(o, Exception):
            r.update(trl="", gvr={"status": "error", "error": str(o)})
            stats["error"] += 1
            continue
        r["trl"] = o["trl"]
        r["gvr"] = {k: o[k] for k in ("status", "attempts", "history")}
        stats[o["status"]] += 1
        stats["repaired"] += o["status"] == "ok" and o["attempts"] > 1
    ctx.save("raft_rules", data)
    return {"summary": {"形式化": stats["ok"], "经修复": stats["repaired"], "丢弃": stats["discarded"], "调用失败": stats["error"]},
            "status": "ok" if stats["ok"] else "needs_review"}


STEP_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 300}, "testable": {"type": "boolean"}},
               "required": ["reason", "testable"]}
STEP_TAIL = "\n\n### JSON 输出\n先用一句话给出理由，再给出 testable（true/false）。"
REFINE_MSG = ("该可测试需求未通过可测试性判定。\n违反的约束：{violations}\n原因：{reason}\n{domain}"
              "请针对这些违反进行有针对性的补全或具体化（例如补充缺失的操作 Action、把模糊的取值具体化为原文给出的确定数值、拆分并列情形），"
              "新增的要素和取值必须能在原文中找到依据，禁止造词；如果原文本身无法提供确定的内容，请原样输出原需求。只输出完整的可测试需求。")


def _judge(ctx: ToolContext, rule: str, trl: str, min_pass: int) -> dict:
    """RAFT five-step determination: one prompt per OCL invariant, early exit once the verdict is fixed."""
    steps = files(ctx)["prompts"]["testability_steps"]
    verdicts = []
    for name, sp in steps.items():
        o = ctx.llm.json([{"role": "system", "content": sp + STEP_TAIL}, {"role": "user", "content": f"{rule}\n{trl}"}], STEP_SCHEMA,
                         max_tokens=400, kind="raft.testability")
        verdicts.append({"constraint": name, "ok": bool(o["testable"]), "reason": o["reason"]})
        passed = sum(v["ok"] for v in verdicts)
        if passed >= min_pass or len(verdicts) - passed > len(steps) - min_pass:
            break
    bad = [v for v in verdicts if not v["ok"]]
    return {"testable": sum(v["ok"] for v in verdicts) >= min_pass, "violations": [v["constraint"] for v in bad],
            "reason": "；".join(v["reason"] for v in bad) or verdicts[-1]["reason"], "steps": verdicts}


@tool("raft.testability", "可测试性判定与精化", W, "testability/prompt/judge_testability_step1-5 (five-step OCL) · refinement with T", "local-llm",
      "按 RAFT 五步提示词逐条检查 5 个 OCL 可测试性约束（通过数 ≥ 阈值判为可测）；违反时注入领域约束 T 做有针对性的补全/具体化并复检"
      "（新增内容必须有原文依据），仍不可测则交由复核/丢弃", ["raft_rules"], ["raft_rules"])
def testability(ctx: ToolContext, rounds: int = 2, min_pass: int | None = None) -> dict:
    pack = _pack(ctx)
    data = ctx.load("raft_rules")
    min_pass = min_pass or ctx.llm.settings.testability_min_pass
    ocl = render_ocl(pack["representation"])
    domain_t = f"领域可测试性约束（知识产物 T）：\n```\n{ocl[:3000]}\n```\n" if ocl else ""
    p_r = _requirement_prompt(ctx, pack)
    for r in data["rules"]:
        r.pop("trl_final", None)
        r.pop("testability", None)
    todo = [r for r in data["rules"] if r.get("trl")]
    doc_text = ctx.load("doc_main")["text"]

    def refine(r, trl, j):
        msgs = [{"role": "system", "content": p_r},
                {"role": "user", "content": f"Generate structured requirements for the following regulatory rule:\n\nRule: {r['rule_cn']}\n\n"},
                {"role": "assistant", "content": trl},
                {"role": "user", "content": REFINE_MSG.format(violations="、".join(j["violations"]) or "未列出", reason=j["reason"], domain=domain_t)}]
        return T.normalize(ctx.llm.chat(msgs, max_tokens=1200, kind="raft.refine"))

    def one(r):
        syms, labels, srcs = _check_ctx(pack, r, doc_text)
        trl = r["trl"]
        j = _judge(ctx, r["rule_cn"], trl, min_pass)
        hist = [{"trl": trl, **j}]
        for _ in range(rounds):
            if j["testable"]:
                break
            cand = refine(r, trl, j)
            if not cand or cand == trl:
                hist.append({"trl": cand, "note": "模型无法在原文依据内精化"})
                break
            chk = T.check(cand, syms, labels, srcs)
            if not chk["ok"]:
                hist.append({"trl": cand, "check_errors": chk["errors"]})
                continue
            trl, j = cand, _judge(ctx, r["rule_cn"], cand, min_pass)
            hist.append({"trl": trl, **j})
        return {"testable": j["testable"], "trl": trl, "judge": j, "refined": j["testable"] and len(hist) > 1, "history": hist}

    out = ctx.llm_map(one, todo, "可测试性")
    n_ok = n_ref = 0
    rejected = []
    for r, o in zip(todo, out):
        if isinstance(o, Exception):
            r["testability"] = {"testable": False, "reason": f"判定失败: {o}", "violations": []}
        else:
            r["testability"] = {"testable": o["testable"], "violations": o["judge"]["violations"], "reason": o["judge"]["reason"],
                                "refined": o["refined"], "history": o["history"]}
            if o["testable"]:
                r["trl_final"] = o["trl"]
                n_ok += 1
                n_ref += o["refined"]
                continue
        rejected.append({"rid": r["rid"], "rule": r["rule_cn"][:300], "trl": r["trl"][:600],
                         "violations": r["testability"]["violations"], "reason": r["testability"]["reason"][:300]})
    ctx.save("raft_rules", data)
    res = {"summary": {"判定": len(todo), "可测试": n_ok, "其中精化后可测": n_ref, "不可测": len(rejected)}}
    if rejected:
        res["review"] = {"kind": "untestable", "items": rejected}
    return res


@tool("raft.accept", "人工复核不可测需求", W, "RAFT HITL variant · expert review of untestable requirements", "human",
      "HITL 变体：判定为不可测的需求交由用户复核；保留的需求标记为人工确认后继续生成测试，其余丢弃（全自动 RAFT 的做法）", ["raft_rules"], ["raft_rules"])
def accept(ctx: ToolContext, keep: list[str] | None = None, policy: str = "custom") -> dict:
    data = ctx.load("raft_rules")
    keep = set(keep or [])
    kept = dropped = 0
    for r in data["rules"]:
        if not r.get("trl") or (r.get("testability") or {}).get("testable"):
            continue
        t = r.setdefault("testability", {})
        if r["rid"] in keep:
            r["trl_final"] = r["trl"]
            t["override"] = "user_kept"
            kept += 1
        else:
            r.pop("trl_final", None)
            t["override"] = "discarded"
            dropped += 1
    ctx.save("raft_rules", data)
    return {"summary": {"策略": policy, "人工保留": kept, "丢弃": dropped}}


@tool("raft.postprocess", "TRL后处理", W, "trl/post_process.py · post_process", "RAFT",
      "去转义、中英键映射（keymap 来自需求表示的中文标签）、not/or 展开、规则重排", ["raft_rules"], ["raft_rules"])
def postprocess(ctx: ToolContext) -> dict:
    pack = _pack(ctx)
    data = ctx.load("raft_rules")
    for r in data["rules"]:
        for k in ("trl_postprocess", "parse", "testcase", "trl_parsed", "sub_tests"):
            r.pop(k, None)
    todo = [r for r in data["rules"] if r.get("trl_final")]
    km = keymap(pack["representation"])
    out = ctx.worker("raft", "postprocess", {"preds": [r["trl_final"] for r in todo], "keymap": km})
    bad = 0
    for i, (r, p) in enumerate(zip(todo, out["trl"])):
        r["trl_postprocess"] = p
        chk = ctx.worker("raft", "parse", {"trl": p, "rule": r["rule_cn"]}) if p else {"ok": False, "error": out["errors"].get(str(i), "empty")}
        r["parse"] = chk
        bad += not chk["ok"]
    ctx.save("raft_rules", data)
    return {"summary": {"后处理": len(todo), "解析失败": bad}}


@tool("raft.generate", "场景与测试用例生成", W, "testcase/generate_testcase.py · generate_testcase (z3)", "RAFT z3",
      "等价类/边界值 + z3 求解生成正反例测试用例；Status→ResultStatus 衔接的需求串成业务场景", ["raft_rules"], ["tests", "raft_scenarios"])
def generate(ctx: ToolContext) -> dict:
    data = ctx.load("raft_rules")
    todo = [r for r in data["rules"] if r.get("trl_postprocess") and r.get("parse", {}).get("ok")]
    res = ctx.worker("raft", "generate", {"items": [{"rule": r["rule_cn"], "predict": r["trl_postprocess"]} for r in todo]})
    groups = []
    for r, o in zip(todo, res["results"]):
        r["testcase"] = o["testcase"]
        r["trl_parsed"] = o["trl"]
        r["sub_tests"] = []
        n = 0
        for j, sub in enumerate(o["subs"], 1):
            g = []
            for tc in sub:
                n += 1
                g.append({"rule": f"{r['rid']}.{j}", "testid": f"{r['rid']}.{j}_{len(g) + 1}", **tc})
            r["sub_tests"].append([t["testid"] for t in g])
            if g:
                groups.append(g)
    scen = _chain(todo)
    ctx.save("raft_rules", data)
    ctx.save("raft_scenarios", scen)
    ctx.save("tests", {"workflow": W, "testcases": groups})
    n = sum(len(g) for g in groups)
    pos = sum(1 for g in groups for t in g if t.get("结果") in ("成功", "可以"))
    return {"summary": {"需求": len(todo), "业务场景链": len(scen["chains"]), "测试用例": n, "正例": pos, "反例": n - pos,
                        "生成失败": len(res["errors"])}}


def _chain(rules: list[dict]) -> dict:
    """RAFT step 7: requirement A precedes B when A's ResultStatus equals B's Status (same business object)."""
    pre, post = {}, {}
    for r in rules:
        for sub in r.get("trl_parsed") or []:
            for c in sub.get("conditions", []):
                if c[0] == "状态" and len(c) > 2:
                    pre.setdefault(r["rid"], set()).add(c[2])
            for c in sub.get("consequences", []):
                if c[0] == "结果状态" and len(c) > 2:
                    post.setdefault(r["rid"], set()).add(c[2])
    edges = [(a, b, sorted(post[a] & pre[b])[0]) for a in post for b in pre if a != b and post[a] & pre[b]]
    nxt = {}
    for a, b, _ in edges:
        nxt.setdefault(a, []).append(b)
    starts = [a for a in nxt if not any(a in v for v in nxt.values())] or list(nxt)
    chains = []

    def walk(path):
        if len(chains) >= 200:
            return
        tail = nxt.get(path[-1], [])
        ext = [b for b in tail if b not in path]
        if not ext:
            if len(path) > 1:
                chains.append(path)
            return
        for b in ext:
            walk(path + [b])

    for s in starts:
        walk([s])
    return {"edges": [{"from": a, "to": b, "state": s} for a, b, s in edges], "chains": chains}
