"""Standard operating procedures: the step sequence of each original workflow, and the
evidence-based routing policy that picks one. The planner never invents steps."""
from __future__ import annotations

from ..tools.base import REGISTRY

PHASES = {"analyze": "分析", "knowledge": "知识工程", "formalize": "需求形式化", "generate": "场景与用例生成",
          "reuse": "测试复用", "verify": "验证"}

SOP = {
    "llm4fin": [
        ("l4f.segment", "formalize"), ("l4f.filter", "formalize"), ("l4f.extract", "formalize"), ("l4f.assemble", "formalize"),
        ("l4f.consistency", "formalize"), ("l4f.complete", "generate"), ("l4f.relate", "generate"), ("l4f.generate", "generate"),
        ("tests.minimize", "generate"),
    ],
    "raft_phase1": [("raft.meta_model", "knowledge"), ("raft.representation", "knowledge"), ("raft.register", "knowledge")],
    "raft_phase2": [
        ("raft.segment", "formalize"), ("raft.translate", "formalize"), ("raft.filter", "formalize"), ("raft.formalize", "formalize"),
        ("raft.testability", "formalize"), ("raft.postprocess", "generate"), ("raft.generate", "generate"),
        ("tests.minimize", "generate"),
    ],
    "care": [
        ("tests.ingest", "reuse"), ("care.requirements_old", "reuse"), ("care.requirements_new", "reuse"), ("care.align", "reuse"),
        ("care.diff", "reuse"), ("care.impact", "reuse"), ("care.update", "reuse"),
    ],
}
OPTIONAL = {"l4f.consistency", "raft.translate", "tests.minimize"}
WORKFLOW_TITLES = {"llm4fin": "LLM4Fin", "raft": "RAFT", "raft_build": "RAFT 知识工程", "care": "CARE"}


def route(intent: str, domain: dict, knowledge: dict, doc_lang: str, hint: str = "auto") -> tuple[str, list[str], list[str]]:
    """Returns (workflow, sop names, reasons). Every reason cites observed evidence."""
    dom = domain.get("domain")
    title = domain.get("title") or dom or "未知领域"
    reasons = []
    if intent == "reuse_tests":
        return "care", ["care"], ["测试复用/维护任务 → CARE：需求生成 → 场景生成 → 用例对齐 → 变更识别 → 影响分析 → 用例更新"]
    if intent == "build_knowledge":
        return "raft_build", ["raft_phase1"], [f"知识工程任务 → RAFT Phase I：为「{title}」构建元模型 M、需求表示 R、可测试性约束 T"]
    found = knowledge.get("found")
    if hint == "llm4fin" and dom == "finance" and doc_lang == "zh":
        return "llm4fin", ["llm4fin"], ["用户指定 LLM4Fin"]
    if dom == "finance" and doc_lang == "zh" and hint != "raft":
        reasons.append(f"领域识别为「{title}」（证据：{'、'.join(domain.get('evidence') or domain.get('hits') or [])[:60] or '关键词'}）")
        reasons.append("知识库命中 LLM4Fin 金融领域知识（分类知识树 / 状态机 / 术语表）及 mengzi 规则筛选与要素抽取模型")
        reasons.append("→ 采用 LLM4Fin 工作流：过滤不可测规则 → 规则元素抽取与形式化 → 补全 → 关系挖掘 → 生成测试")
        return "llm4fin", ["llm4fin"], reasons
    if dom and found:
        reasons.append(f"领域识别为「{title}」，知识库已有 RAFT 知识（来源：{knowledge.get('source')}）")
        if dom == "finance":
            reasons.append(f"文档语言为 {doc_lang}，LLM4Fin 的 mengzi 模型只支持中文规则 → 使用 RAFT 金融知识" if doc_lang != "zh" else "用户指定 RAFT")
        reasons.append("→ 采用 RAFT Phase II：知识注入的需求形式化 → 可测试性判定与精化 → 场景与用例生成")
        return "raft", ["raft_phase2"], reasons
    reasons.append(f"领域「{title}」在知识库中没有可用知识" if dom else "未能确定领域，也没有匹配的领域知识")
    reasons.append("→ 先用 RAFT Phase I 进行知识工程（元模型 → 需求表示/可测试性约束 → 登记知识），再用 RAFT Phase II 生成测试")
    return "raft", ["raft_phase1", "raft_phase2"], reasons


def build_steps(sops: list[str], lang: str, opts: dict) -> list[dict]:
    steps = []
    for sop in sops:
        for name, phase in SOP[sop]:
            if name == "raft.translate" and lang == "zh":
                continue
            if name == "l4f.consistency" and opts.get("skip_consistency"):
                continue
            if name == "tests.minimize" and not opts.get("minimize"):
                continue  # opt-in: full suite stays canonical unless the user enables minimization
            t = REGISTRY[name]
            args = {}
            if name == "raft.segment" and opts.get("max_rules"):
                args["max_rules"] = int(opts["max_rules"])
            steps.append({"id": f"s{len(steps) + 1}", "tool": name, "title": t.title, "phase": phase, "workflow": t.workflow,
                          "origin": t.origin, "backend": t.backend, "desc": t.desc, "args": args, "optional": name in OPTIONAL,
                          "status": "pending"})
    return steps
