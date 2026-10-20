"""LangGraph agent.

understand → gather ⇄(interrupt: missing inputs) → analyze → [ask_domain(interrupt) → redetect] → plan
→ execute ⟲ (per SOP step; failure → on_failure(interrupt: retry/skip/abort)) → verify → report

The planner only selects one of the original workflows' SOPs (agent/sop.py) from observed evidence
(domain detection + knowledge lookup); the executor runs each SOP step as an audited tool call.
Interrupts live in side-effect-free nodes because LangGraph re-runs a node when it resumes."""
from __future__ import annotations

import json
import operator
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Annotated, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from .. import views
from ..config import Settings, get_settings
from ..knowledge import KnowledgeBase
from ..llm import LLM, LLMError
from ..store import Store
from ..tools import REGISTRY, Cancelled, ToolContext, ToolFailed, run_tool
from ..workers.client import Pool
from . import verify as V
from .memory import PREF_KEYS, Memory
from .sop import PHASES, WORKFLOW_TITLES, build_steps, route

INTENTS = ["generate_tests", "reuse_tests", "build_knowledge", "query", "remember", "chat"]
INTENT_TITLES = {"generate_tests": "生成测试用例", "reuse_tests": "测试复用/维护", "build_knowledge": "领域知识工程",
                 "query": "查询", "remember": "记住偏好", "chat": "对话"}
USED_PREFS = {"llm4fin": {"judge_samples", "minimize"}, "raft": {"judge_samples", "max_rules", "untestable_policy", "minimize"}, "care": {"judge_samples"},
              "raft_build": set()}  # which remembered preferences each workflow actually consumes (shown in the plan)


class AgentState(TypedDict, total=False):
    request: str
    files: list[dict]
    intent: str
    params: dict
    roles: dict
    domain: dict
    knowledge: dict
    analysis: list
    need_domain: bool
    workflow: str
    plan: dict
    cursor: int
    failed: dict
    review: dict
    run_id: str
    verification: dict
    reply: str
    history: Annotated[list, operator.add]


@dataclass
class Deps:
    store: Store
    pool: Pool
    llm: LLM
    memory: Memory
    kb: KnowledgeBase
    thread_id: str
    emit: Callable[[str, dict], None]
    cancelled: Callable[[], bool] = lambda: False
    settings: Settings = field(default_factory=get_settings)


UNDERSTAND_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "workflow_hint": {"type": "string", "enum": ["auto", "llm4fin", "raft"]},
        "domain_hint": {"type": "string", "maxLength": 30},
        "roles": {"type": "array", "items": {"type": "object", "properties": {
            "file": {"type": "string"}, "role": {"type": "string", "enum": ["main", "old_rules", "new_rules", "old_tests", "other"]}},
            "required": ["file", "role"]}},
        "remember": {"type": "array", "items": {"type": "object", "properties": {
            "key": {"type": "string", "enum": list(PREF_KEYS)}, "value": {"type": "string", "maxLength": 100}}, "required": ["key", "value"]}},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["intent", "workflow_hint", "domain_hint", "roles", "remember", "reason"],
}
UNDERSTAND_SYS = """你是“法规测试智能体”的意图理解模块。可选意图：
- generate_tests：根据规则/标准文档生成测试用例（含需求形式化、场景）。
- reuse_tests：规则修订后复用/维护/更新已有测试用例（需要原规则、新规则、原测试用例）。
- build_knowledge：为某领域做知识工程（构建元模型、需求表示、可测试性约束），不一定生成测试。
- query：询问已有结果、知识库、历史任务或系统能力。
- remember：要求记住某个偏好（如默认工作流、抽检数量）。
- chat：其他闲聊或说明。
为每个附件判断角色：main（待生成测试的文档）、old_rules（修订前规则）、new_rules（修订后规则）、old_tests（原测试用例，通常是 .json）、other。
文件名中的“修订前/旧/2021”等提示 old_rules，“修订后/新/2023”等提示 new_rules；json 测试用例文件为 old_tests。
workflow_hint 只有用户明确点名 LLM4Fin 或 RAFT 时才填写，否则 auto。remember 只在用户明确要求“记住”时填写。只依据用户原话和文件名，不要臆测。"""


def _files_desc(files: list[dict]) -> str:
    return "\n".join(f"- {f['name']}（{f.get('ext', '')}, {f.get('size', 0)} 字节）" for f in files) or "（无附件）"


def _rule_based_roles(files: list[dict], intent: str) -> dict:
    roles: dict[str, str] = {}
    for f in files:
        n = f["name"].lower()
        if n.endswith(".json"):
            roles[f["id"]] = "old_tests"
        elif intent == "reuse_tests":
            if re.search(r"(旧|原|修订前|old|v1|2019|2020|2021)", n):
                roles[f["id"]] = "old_rules"
            elif re.search(r"(新|修订后|new|v2|2022|2023|2024|2025)", n):
                roles[f["id"]] = "new_rules"
        else:
            roles[f["id"]] = "main"
    return roles


def _fold_roles(files: list[dict], llm_roles: list[dict], intent: str) -> dict:
    by_name = {f["name"]: f["id"] for f in files}
    roles = _rule_based_roles(files, intent)
    for r in llm_roles:
        fid = by_name.get(r["file"]) or next((f["id"] for f in files if r["file"] and r["file"] in f["name"]), None)
        if fid and r["role"] != "other":
            if roles.get(fid) == "old_tests" and r["role"] != "old_tests":
                continue
            if intent != "reuse_tests" and r["role"] in ("old_rules", "new_rules"):
                continue
            roles[fid] = r["role"]
    if intent == "reuse_tests":
        docs = [f for f in files if not f["name"].lower().endswith(".json")]
        rr = [roles.get(f["id"]) for f in docs]
        if len(docs) == 2 and sorted(rr, key=str) != ["new_rules", "old_rules"]:  # fall back to upload order
            roles[docs[0]["id"]], roles[docs[1]["id"]] = "old_rules", "new_rules"
    return roles


def _role_file(state: AgentState, role: str) -> dict | None:
    for f in state.get("files", []):
        if state.get("roles", {}).get(f["id"]) == role:
            return f
    return None


def _missing(state: AgentState) -> list[str]:
    it = state.get("intent")
    if it == "reuse_tests":
        need = [("old_rules", "原规则文档"), ("new_rules", "新规则文档"), ("old_tests", "原测试用例（JSON）")]
        return [label for role, label in need if not _role_file(state, role)]
    if it in ("generate_tests", "build_knowledge"):
        return [] if _role_file(state, "main") else ["规则/标准文档"]
    return []


def _ctx(d: Deps, rid: str, step_id: str) -> ToolContext:
    return ToolContext(run_id=rid, thread_id=d.thread_id, store=d.store, pool=d.pool, llm=d.llm, memory=d.memory, step_id=step_id,
                       emit=lambda t, data: d.emit(t, {**data, "run_id": rid}), cancelled=d.cancelled)


def _analysis_step(name: str, out: dict) -> dict:
    t = REGISTRY[name]
    return {"tool": name, "title": t.title, "phase": "analyze", "workflow": t.workflow, "origin": t.origin, "backend": t.backend,
            "desc": t.desc, "status": out.get("status", "ok"), "summary": out.get("summary"), "seconds": out.get("seconds"), "llm": out.get("llm")}


# ------------------------------------------------------------------ nodes --
def n_understand(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    d.emit("phase", {"phase": "understand", "status": "running"})
    recall = d.memory.recall(d.thread_id)
    recent = [{k: e.get(k) for k in ("intent", "workflow", "domain", "verdict", "docs")} for e in recall["recent"][:3]]
    msgs = [{"role": "system", "content": UNDERSTAND_SYS},
            {"role": "user", "content": f"用户请求：{state['request']}\n附件：\n{_files_desc(state.get('files', []))}\n"
                                        f"本会话最近任务：{json.dumps(recent, ensure_ascii=False)}"}]
    try:
        u = d.llm.json(msgs, UNDERSTAND_SCHEMA, max_tokens=600, kind="understand")
    except LLMError as e:
        has_doc = any(not f["name"].lower().endswith(".json") for f in state.get("files", []))
        u = {"intent": "generate_tests" if has_doc else "chat", "workflow_hint": "auto", "domain_hint": "", "roles": [], "remember": [],
             "reason": f"本地模型不可用，按附件规则推断（{e}）"}
    intent = u["intent"]
    if intent in ("chat", "query") and state.get("files") and re.search(r"(生成|测试|用例|复用|更新|维护|知识)", state["request"]):
        intent = "reuse_tests" if re.search(r"(复用|更新|维护|修订|变更)", state["request"]) else "generate_tests"
    roles = _fold_roles(state.get("files", []), u["roles"], intent)
    prefs = recall["prefs"]
    params = {"workflow_hint": u["workflow_hint"], "domain_hint": u["domain_hint"], **{k: v for k, v in prefs.items() if v}}
    default_wf = str(prefs.get("default_workflow") or "").strip().lower()
    if default_wf in ("llm4fin", "raft") and u["workflow_hint"] == "auto":
        params["workflow_hint"] = params["default_workflow"] = default_wf
    for r in u["remember"]:
        d.memory.set_pref(r["key"], r["value"], source=state["request"][:200])
    d.emit("phase", {"phase": "understand", "status": "done", "intent": intent, "intent_title": INTENT_TITLES[intent], "reason": u["reason"],
                     "roles": {f["name"]: roles.get(f["id"]) for f in state.get("files", [])}, "remembered": u["remember"],
                     "prefs_used": {k: v for k, v in prefs.items() if v}})
    return {"intent": intent, "roles": roles, "params": params, "history": [{"node": "understand", "intent": intent, "reason": u["reason"]}]}


def n_gather(state: AgentState, runtime: Runtime[Deps]) -> dict:
    miss = _missing(state)
    if not miss:
        return {}
    files = state.get("files", [])
    runtime.context.emit("phase", {"phase": "gather", "status": "waiting", "missing": miss})
    ans = interrupt({"kind": "need_inputs", "intent": state["intent"], "intent_title": INTENT_TITLES[state["intent"]], "missing": miss,
                     "question": f"要执行「{INTENT_TITLES[state['intent']]}」，还需要：{'、'.join(miss)}。请上传对应文件（或补充说明）后继续。",
                     "files": [{"id": f["id"], "name": f["name"], "role": state.get("roles", {}).get(f["id"])} for f in files]}) or {}
    new_files = files + [f for f in ans.get("files", []) if f["id"] not in {x["id"] for x in files}]
    roles = dict(state.get("roles", {}))
    for fid, r in _fold_roles(new_files, [], state["intent"]).items():
        roles.setdefault(fid, r)
    if state["intent"] == "reuse_tests" and ans.get("files"):
        roles.update({k: v for k, v in _fold_roles(new_files, [], "reuse_tests").items() if k not in roles or roles[k] is None})
    roles.update(ans.get("roles") or {})
    req = state["request"] + (("\n补充：" + ans["text"]) if ans.get("text") else "")
    return {"files": new_files, "roles": roles, "request": req, "history": [{"node": "gather", "files": [f["name"] for f in ans.get("files", [])]}]}


def after_gather(state: AgentState) -> str:
    if state["intent"] in ("chat", "query", "remember"):
        return "respond"
    return "gather" if _missing(state) else "analyze"


def n_respond(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    info = {"knowledge": d.kb.list(), "recent_tasks": d.memory.episodes(d.thread_id, 5), "prefs": d.memory.prefs(),
            "runs": [{k: r.get(k) for k in ("id", "workflow", "domain", "status")} | {"stats": (r.get("summary") or {}).get("stats")}
                     for r in d.store.runs(d.thread_id)[:5]]}
    sys = ("你是法规测试智能体，能力：①用 LLM4Fin 工作流为金融（证券）中文规则生成测试；②用 RAFT 为陌生领域做知识工程（元模型/需求表示/可测试性约束）并生成测试；"
           "③用 CARE 在规则修订后复用和更新测试用例。只依据给定上下文回答，不要编造任务结果；用中文简洁回答。")
    try:
        reply = d.llm.chat([{"role": "system", "content": sys},
                            {"role": "user", "content": f"上下文：{json.dumps(info, ensure_ascii=False, default=str)[:12000]}\n\n用户：{state['request']}"}],
                           max_tokens=800, kind="respond")
    except LLMError as e:
        reply = f"本地模型暂不可用（{e}）。可以：上传规则文档生成测试；上传原规则/新规则/原用例做测试复用；或让我为某领域构建知识。"
    if state["intent"] == "remember":
        reply = "已记住偏好：" + json.dumps(d.memory.prefs(), ensure_ascii=False) + "\n\n" + reply
    return {"reply": reply}


def n_analyze(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    d.emit("phase", {"phase": "analyze", "status": "running"})
    rid = d.store.create_run(d.thread_id, "pending", "", {"request": state["request"]})
    ctx = _ctx(d, rid, "analyze")
    steps = []
    for role, art in (("main", "main"), ("old_rules", "old"), ("new_rules", "new")):
        f = _role_file(state, role)
        if f:
            steps.append(_analysis_step("doc.ingest", run_tool(ctx, "doc.ingest", {"path": f["path"], "name": f["name"], "role": art})))
    domain, need = {}, False
    if state["intent"] in ("generate_tests", "build_knowledge"):
        out = run_tool(ctx, "domain.detect", {"role": "main", "hint": state["params"].get("domain_hint", "")})
        steps.append(_analysis_step("domain.detect", out))
        domain, need = out["domain"], not out["domain"].get("domain")
    else:
        out = run_tool(ctx, "domain.detect", {"role": "new"})
        steps.append(_analysis_step("domain.detect", out))
        domain = {**out["domain"], "domain": "finance", "title": "金融（证券交易）", "detected": out["domain"].get("domain")}
        ctx.save("domain", domain)
    return {"run_id": rid, "domain": domain, "analysis": steps, "need_domain": need}


def after_analyze(state: AgentState) -> str:
    return "ask_domain" if state.get("need_domain") else "lookup"


def n_ask_domain(state: AgentState, runtime: Runtime[Deps]) -> dict:
    ans = interrupt({"kind": "need_domain", "question": "未能从文档中确定所属领域。请告诉我它属于哪个领域（例如：金融证券、道路交通、电力并网，或其他领域名称）。",
                     "scores": {k: v["score"] for k, v in (state["domain"].get("scores") or {}).items()}}) or {}
    return {"params": {**state["params"], "domain_hint": ans.get("text", "")}, "history": [{"node": "ask_domain", "answer": ans.get("text", "")}]}


def n_redetect(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    ctx = _ctx(d, state["run_id"], "analyze")
    hint = state["params"].get("domain_hint", "")
    out = run_tool(ctx, "domain.detect", {"role": "main", "hint": hint})
    domain = out["domain"]
    if not domain.get("domain"):
        slug = re.sub(r"[^a-z0-9]", "", hint.lower())[:20] or f"domain{int(time.time()) % 100000}"
        domain = {"domain": slug, "title": hint[:20] or slug, "is_new": True, "keywords": [hint[:10]] if hint else [], "method": "user", "evidence": []}
        ctx.save("domain", domain)
    return {"domain": domain, "analysis": state["analysis"] + [_analysis_step("domain.detect", out)], "need_domain": False}


def n_lookup(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    ctx = _ctx(d, state["run_id"], "analyze")
    out = run_tool(ctx, "knowledge.lookup", {"domain": state["domain"].get("domain")})
    d.emit("phase", {"phase": "analyze", "status": "done", "domain": state["domain"], "knowledge": out["knowledge"]})
    return {"knowledge": out["knowledge"], "analysis": state["analysis"] + [_analysis_step("knowledge.lookup", out)]}


def n_plan(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    rid = state["run_id"]
    doc = d.store.load(rid, "doc_main") or d.store.load(rid, "doc_new") or {}
    lang = doc.get("lang", "zh")
    workflow, sops, reasons = route(state["intent"], state["domain"], state["knowledge"], lang, state["params"].get("workflow_hint", "auto"))
    if state["intent"] == "build_knowledge" and state["knowledge"].get("found"):
        reasons.append(f"注意：该领域已有知识（来源 {state['knowledge'].get('source')}），本次构建会覆盖更新")
    if state["intent"] == "reuse_tests" and state["domain"].get("detected") not in (None, "finance"):
        reasons.append(f"注意：新规则文档更像「{state['domain'].get('detected')}」领域，CARE 的知识与模型面向中文证券规则，结果需人工复核")
    steps = build_steps(sops, lang, {"max_rules": state["params"].get("max_rules"),
                                      "minimize": str(state["params"].get("minimize") or "").lower() in ("1", "true", "yes", "on", "是")})
    for i, s in enumerate(state.get("analysis", [])):
        s["id"] = f"a{i + 1}"
    steps = state.get("analysis", []) + steps
    seen = [r for r in doc.get("seen", []) if r.get("workflow") == workflow and r.get("run_id") != rid]
    used = USED_PREFS.get(workflow, set()) | ({"default_workflow"} if state["params"].get("default_workflow") == workflow else set())
    plan = {"workflow": workflow, "title": WORKFLOW_TITLES[workflow], "sops": sops, "reasons": reasons, "steps": steps,
            "domain": {k: state["domain"].get(k) for k in ("domain", "title", "method", "evidence", "is_new")},
            "intent": state["intent"], "intent_title": INTENT_TITLES[state["intent"]], "lang": lang,
            "phases": ["analyze"] + [p for p in PHASES if p != "analyze" and any(s["phase"] == p for s in steps)] + ["verify"],
            "memory": {"same_doc_runs": seen[-3:], "prefs": {k: v for k, v in state["params"].items() if k in used and v}}}
    d.store.update_run(rid, workflow="raft" if workflow == "raft_build" else workflow, domain=state["domain"].get("domain") or "", plan=plan)
    d.emit("plan", {**plan, "run_id": rid})
    return {"plan": plan, "workflow": workflow, "cursor": len(state.get("analysis", [])), "history": [{"node": "plan", "workflow": workflow}]}


def n_execute(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    plan = json.loads(json.dumps(state["plan"]))
    i = state["cursor"]
    step = plan["steps"][i]
    ctx = _ctx(d, state["run_id"], step["id"])
    step.update(status="running", started=time.time(), error=None)
    d.store.update_run(state["run_id"], plan=plan)  # a page opened mid-step shows it as running
    d.emit("step", {"index": i, **step, "run_id": state["run_id"]})
    args = dict(step.get("args") or {})
    if step["tool"] == "tests.ingest":
        f = _role_file(state, "old_tests")
        args.update(path=f["path"], name=f["name"])
    failed = None
    review = None
    try:
        out = run_tool(ctx, step["tool"], args)
        step.update(status=out.get("status", "ok"), summary=out.get("summary"), seconds=out.get("seconds"), llm=out.get("llm"))
        cursor = i + 1
        if out.get("review"):
            policy = str(state["params"].get("untestable_policy") or "ask").lower()
            if policy in ("strict", "keep"):
                keep = [x["rid"] for x in out["review"]["items"]] if policy == "keep" else []
                acc = run_tool(_ctx(d, state["run_id"], step["id"]), "raft.accept", {"keep": keep, "policy": f"偏好:{policy}"})
                step["review"] = {"policy": policy, "summary": acc["summary"]}
            else:
                review = {"index": i, **out["review"]}
                step["status"] = "review"
    except Cancelled:
        step.update(status="cancelled")
        cursor = len(plan["steps"])
        failed = {"cancelled": True}
    except ToolFailed as e:
        step.update(status="error", error=str(e)[:2000], seconds=round(time.time() - step["started"], 2))
        cursor = i + 1 if step.get("optional") else i
        failed = None if step.get("optional") else {"index": i, "error": str(e)[:2000]}
    plan["steps"][i] = step
    d.emit("step", {"index": i, **step, "run_id": state["run_id"]})
    d.store.update_run(state["run_id"], plan=plan)
    return {"plan": plan, "cursor": cursor, "failed": failed, "review": review,
            "history": [{"node": "execute", "tool": step["tool"], "status": step["status"]}]}


def after_execute(state: AgentState) -> str:
    f = state.get("failed")
    if f and f.get("cancelled"):
        return "report"
    if f:
        return "on_failure"
    if state.get("review"):
        return "review"
    return "execute" if state["cursor"] < len(state["plan"]["steps"]) else "verify"


def n_review(state: AgentState, runtime: Runtime[Deps]) -> dict:
    """RAFT HITL variant: the user decides which untestable requirements to keep (pure interrupt node)."""
    rv = state["review"]
    items = rv["items"]
    ans = interrupt({"kind": "review_untestable", "count": len(items), "items": items[:60],
                     "question": f"可测试性判定后有 {len(items)} 条需求被判为不可测（违反 OCL 约束）。全自动 RAFT 会丢弃它们；"
                                 f"你可以勾选要保留的需求（人工确认后继续生成测试），或直接全部丢弃。",
                     "options": [{"value": "drop", "label": "全部丢弃（全自动 RAFT）"}, {"value": "keep_all", "label": "全部保留待复核"},
                                 {"value": "custom", "label": "按勾选保留"}]}) or {}
    choice = (ans.get("choice") or ans.get("text") or "drop").lower()
    if "keep_all" in choice or "全部保留" in choice:
        keep = [x["rid"] for x in items]
    elif ans.get("keep"):
        keep = [k for k in ans["keep"] if k in {x["rid"] for x in items}]
    else:
        keep = re.findall(r"R\d+", ans.get("text", "")) if "保留" in ans.get("text", "") else []
    return {"review": {**rv, "decided": True, "keep": keep, "choice": choice}}


def n_apply_review(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    rv = state["review"]
    plan = json.loads(json.dumps(state["plan"]))
    step = plan["steps"][rv["index"]]
    acc = run_tool(_ctx(d, state["run_id"], step["id"]), "raft.accept", {"keep": rv["keep"], "policy": rv["choice"]})
    step.update(status="ok", review={"policy": rv["choice"], "summary": acc["summary"]})
    d.emit("step", {"index": rv["index"], **step, "run_id": state["run_id"]})
    d.store.update_run(state["run_id"], plan=plan)
    return {"plan": plan, "review": None, "history": [{"node": "review", "kept": len(rv["keep"])}]}


def after_review(state: AgentState) -> str:
    return "execute" if state["cursor"] < len(state["plan"]["steps"]) else "verify"


def n_on_failure(state: AgentState, runtime: Runtime[Deps]) -> dict:
    f = state["failed"]
    step = state["plan"]["steps"][f["index"]]
    ans = interrupt({"kind": "step_failed", "step": step["title"], "tool": step["tool"], "error": f["error"],
                     "question": f"步骤「{step['title']}」失败：{f['error'][:300]}\n要重试、跳过这一步，还是终止任务？",
                     "options": [{"value": "retry", "label": "重试"}, {"value": "skip", "label": "跳过"}, {"value": "abort", "label": "终止"}]}) or {}
    choice = (ans.get("choice") or ans.get("text") or "abort").lower()
    plan = json.loads(json.dumps(state["plan"]))
    if "retry" in choice or "重试" in choice:
        return {"failed": None, "cursor": f["index"], "history": [{"node": "on_failure", "choice": "retry"}]}
    if "skip" in choice or "跳过" in choice:
        plan["steps"][f["index"]]["status"] = "skipped"
        return {"failed": None, "plan": plan, "cursor": f["index"] + 1, "history": [{"node": "on_failure", "choice": "skip"}]}
    for s in plan["steps"][f["index"] + 1:]:
        s["status"] = "not_run"
    return {"failed": {"aborted": True}, "plan": plan, "cursor": len(plan["steps"]),
            "verification": {"verdict": "fail", "checks": [{"name": "任务终止", "ok": False, "level": "error", "detail": f"在「{step['title']}」处终止"}], "reviews": []},
            "history": [{"node": "on_failure", "choice": "abort"}]}


def after_failure(state: AgentState) -> str:
    if (state.get("failed") or {}).get("aborted"):
        return "report"
    return "execute" if state["cursor"] < len(state["plan"]["steps"]) else "verify"


def n_verify(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    wf = state["workflow"]
    ctx = _ctx(d, state["run_id"], "verify")
    d.emit("phase", {"phase": "verify", "status": "running"})
    t0 = time.time()
    if wf == "raft_build":
        pack = d.kb.get(state["domain"]["domain"]) or {}
        mm, rep = pack.get("meta_model") or {}, pack.get("representation") or {}
        ents = mm.get("entities", {})
        syms = {x for xs in rep.get("symbols", {}).values() for x in xs}
        checks = [{"name": "知识已登记", "ok": bool(pack), "level": "error", "detail": pack.get("domain", "无")},
                  {"name": "元模型要素数(约15)", "ok": 8 <= len(ents) <= 25, "level": "warn", "detail": f"{len(ents)} 个要素"},
                  {"name": "三层结构完整", "ok": all(any(v == l for v in ents.values()) for l in ("Precondition", "Operation", "ExpectedResult")),
                   "level": "error", "detail": "Precondition / Operation / ExpectedResult 均需有要素"},
                  {"name": "需求表示覆盖元模型", "ok": set(ents) <= syms, "level": "warn", "detail": f"{len(set(ents) & syms)}/{len(ents)} 个要素有领域符号"},
                  {"name": "可测试性约束", "ok": len(rep.get("ocl", [])) >= 3, "level": "warn", "detail": f"{len(rep.get('ocl', []))} 条 OCL"}]
        reviews = []
    else:
        checks = V.deterministic(ctx, wf)
        n = int(state["params"].get("judge_samples") or d.settings.judge_samples)
        reviews = []
        if n > 0 and any(c["name"] == "生成测试用例" and c["ok"] for c in checks):
            try:
                reviews = V.judge(ctx, wf, n)
            except (LLMError, Cancelled) as e:
                checks.append({"name": "本地模型抽检", "ok": False, "level": "warn", "detail": f"未完成：{e}"})
    res = {"verdict": V.verdict(checks, reviews), "checks": checks, "reviews": reviews}
    res["reason"] = V.explain(checks, reviews, res["verdict"])
    ctx.save("verification", res)
    d.store.audit(state["run_id"], d.thread_id, "verify", "verify", res["verdict"], time.time() - t0, 1,
                  {"checks": checks, "reviews": len(reviews), "backend": "local-llm judge + deterministic"})
    d.emit("phase", {"phase": "verify", "status": "done", **res, "run_id": state["run_id"]})
    return {"verification": res}


def n_report(state: AgentState, runtime: Runtime[Deps]) -> dict:
    d = runtime.context
    rid = state["run_id"]
    plan = state.get("plan") or {}
    ver = state.get("verification") or {"verdict": "cancelled" if (state.get("failed") or {}).get("cancelled") else "fail"}
    tr = views.trace(d.store, rid) if plan.get("workflow") != "raft_build" else {"stats": {}, "status": {}}
    summary = {"workflow": plan.get("workflow"), "domain": (state.get("domain") or {}).get("domain"), "stats": tr.get("stats"),
               "status": tr.get("status"), "verdict": ver.get("verdict"),
               "steps": [{k: s.get(k) for k in ("tool", "title", "status", "seconds", "summary")} for s in plan.get("steps", [])]}
    d.store.finish_run(rid, ver.get("verdict") or "done", summary)
    doc = d.store.load(rid, "doc_main") or d.store.load(rid, "doc_new") or {}
    if doc.get("sha"):
        d.memory.link_doc(doc["sha"], doc["name"], rid, plan.get("workflow", ""), ver.get("verdict", ""))
    d.memory.add_episode(d.thread_id, rid, {"request": state["request"][:300], "intent": state.get("intent"), "workflow": plan.get("workflow"),
                                            "domain": summary["domain"], "verdict": ver.get("verdict"), "stats": tr.get("stats"),
                                            "docs": [f["name"] for f in state.get("files", [])]})
    return {"reply": _report_text(plan, tr, ver), "verification": ver}


def _report_text(plan: dict, tr: dict, ver: dict) -> str:
    st = tr.get("stats") or {}
    verdict = {"pass": "✅ 通过", "needs_review": "⚠️ 需要人工复核", "fail": "❌ 未通过", "cancelled": "⏹ 已取消"}.get(ver.get("verdict"), ver.get("verdict"))
    lines = [f"**{plan.get('title', '')}** 任务结束 · 验证结论：{verdict}"]
    if ver.get("reason"):
        lines.append(ver["reason"])
    if plan.get("workflow") == "raft_build":
        lines.append("知识工程已完成并登记到知识库，可在「知识」页查看元模型、领域符号与可测试性约束。")
    else:
        lines.append(f"规则 {st.get('rule', 0)} · 需求 {st.get('requirement', 0)} · 场景 {st.get('scenario', 0)} · 测试用例 {st.get('testcase', 0)}")
    if plan.get("workflow") == "care":
        s = tr.get("status") or {}
        lines.append(f"用例：直接复用 {s.get('testcase:reused', 0)} · 重映射 {s.get('testcase:remapped', 0)} · 新生成 {s.get('testcase:added', 0)} · 删除 {s.get('testcase:deleted', 0)}")
    bad = [c for c in ver.get("checks", []) if not c["ok"]]
    if bad:
        lines.append("需关注：" + "；".join(f"{c['name']}（{c['detail']}）" for c in bad[:4]))
    rv = ver.get("reviews") or []
    if rv:
        lines.append(f"本地模型抽检 {len(rv)} 条：忠实 {sum(r['faithful'] == 'yes' for r in rv)} · 存疑 {sum(r['faithful'] == 'uncertain' for r in rv)} · "
                     f"不忠实 {sum(r['faithful'] == 'no' for r in rv)}；用例与需求不一致 {sum(r['tests_consistent'] == 'no' for r in rv)}")
    errs = [s for s in plan.get("steps", []) if s.get("status") in ("error", "skipped", "not_run")]
    if errs:
        lines.append("未完成步骤：" + "、".join(f"{s['title']}（{s['status']}）" for s in errs))
    return "\n".join(lines)


def build_graph() -> StateGraph:
    g = StateGraph(AgentState, context_schema=Deps)
    for name, fn in (("understand", n_understand), ("gather", n_gather), ("respond", n_respond), ("analyze", n_analyze),
                     ("ask_domain", n_ask_domain), ("redetect", n_redetect), ("lookup", n_lookup), ("plan", n_plan),
                     ("execute", n_execute), ("on_failure", n_on_failure), ("review", n_review), ("apply_review", n_apply_review),
                     ("verify", n_verify), ("report", n_report)):
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_edge("understand", "gather")
    g.add_conditional_edges("gather", after_gather, ["respond", "gather", "analyze"])
    g.add_edge("respond", END)
    g.add_conditional_edges("analyze", after_analyze, ["ask_domain", "lookup"])
    g.add_edge("ask_domain", "redetect")
    g.add_edge("redetect", "lookup")
    g.add_edge("lookup", "plan")
    g.add_edge("plan", "execute")
    g.add_conditional_edges("execute", after_execute, ["execute", "on_failure", "review", "verify", "report"])
    g.add_edge("review", "apply_review")
    g.add_conditional_edges("apply_review", after_review, ["execute", "verify"])
    g.add_conditional_edges("on_failure", after_failure, ["execute", "verify", "report"])
    g.add_edge("verify", "report")
    g.add_edge("report", END)
    return g


_saver: SqliteSaver | None = None
_lock = threading.Lock()


def compile_app(settings: Settings | None = None):
    global _saver
    with _lock:
        if _saver is None:
            s = settings or get_settings()
            _saver = SqliteSaver(sqlite3.connect(s.checkpoint_path, check_same_thread=False))
    return build_graph().compile(checkpointer=_saver)


def graph_spec() -> dict:
    """Agent topology for the UI (nodes + edges of the LangGraph)."""
    g = build_graph().compile().get_graph()
    return {"nodes": [{"id": n} for n in g.nodes], "edges": [{"source": e.source, "target": e.target, "conditional": e.conditional} for e in g.edges]}
