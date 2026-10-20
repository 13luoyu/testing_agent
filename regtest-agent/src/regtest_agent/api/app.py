"""FastAPI service: threads / messages / interrupts, SSE event stream, run artifacts and views, knowledge, memory."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import views
from ..agent.graph import INTENT_TITLES, graph_spec
from ..agent.memory import PREF_KEYS
from ..agent.sop import PHASES, SOP, WORKFLOW_TITLES
from ..service import Service
from ..tools import REGISTRY

WEB = Path(__file__).resolve().parents[1] / "web"
svc: Service | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global svc
    svc = Service()
    yield
    svc.close()


app = FastAPI(title="RegTest Agent", version="2.0.0", lifespan=lifespan)


def S() -> Service:
    if svc is None:
        raise HTTPException(503, "服务尚未就绪")
    return svc


def _thread(tid: str) -> dict:
    th = S().store.thread(tid)
    if not th:
        raise HTTPException(404, "会话不存在")
    return th


def _run(rid: str) -> dict:
    r = S().store.run(rid)
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@app.exception_handler(RuntimeError)
async def _busy(_: Request, e: RuntimeError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(ValueError)
async def _bad(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


# ---------------------------------------------------------------- system --
@app.get("/api/health")
def health():
    return S().health()


@app.get("/api/meta")
def meta():
    """Static descriptions the UI needs: agent topology, SOPs, tools, phases, preference keys."""
    return {"graph": graph_spec(), "sops": {k: [{"tool": t, "phase": p} for t, p in v] for k, v in SOP.items()},
            "tools": [t.info() for t in REGISTRY.values()], "phases": PHASES, "workflows": WORKFLOW_TITLES,
            "intents": INTENT_TITLES, "pref_keys": PREF_KEYS}


# --------------------------------------------------------------- threads --
@app.get("/api/threads")
def threads():
    return S().store.threads()


@app.post("/api/threads")
def create_thread():
    return S().store.create_thread()


@app.get("/api/threads/{tid}")
def thread(tid: str):
    th = _thread(tid)
    s = S()
    return {**th, "messages": s.store.messages(tid), "pending": s.pending(tid), "busy": s.busy(tid), "last_seq": s.store.last_seq(tid),
            "runs": [{k: r.get(k) for k in ("id", "workflow", "domain", "status", "started", "ended")} for r in s.store.runs(tid)]}


@app.patch("/api/threads/{tid}")
async def rename_thread(tid: str, req: Request):
    _thread(tid)
    body = await req.json()
    S().store.update_thread(tid, title=str(body.get("title", ""))[:60] or "新对话")
    return S().store.thread(tid)


@app.delete("/api/threads/{tid}")
def delete_thread(tid: str):
    _thread(tid)
    S().delete_thread(tid)
    return {"deleted": tid}


@app.post("/api/threads/{tid}/messages")
async def send(tid: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    _thread(tid)
    s = S()
    saved = [s.save_upload(tid, f.filename or "file", await f.read()) for f in files]
    if not text.strip() and not saved:
        raise HTTPException(400, "消息为空")
    return s.send(tid, text, saved)


@app.post("/api/threads/{tid}/resume")
async def resume(tid: str, req: Request):
    """Answer the pending interrupt: {choice?, text?, keep?, roles?, label?}."""
    _thread(tid)
    return S().resume(tid, await req.json())


@app.post("/api/threads/{tid}/upload")
async def upload(tid: str, files: list[UploadFile] = File(...)):
    _thread(tid)
    return [S().save_upload(tid, f.filename or "file", await f.read()) for f in files]


@app.post("/api/threads/{tid}/stop")
def stop(tid: str):
    _thread(tid)
    return S().stop(tid)


@app.get("/api/threads/{tid}/events")
async def events(tid: str, request: Request, after: int = 0, follow: bool = True):
    """SSE stream; replays from `after` (or Last-Event-ID) and then follows live events (`follow=0`: replay only)."""
    _thread(tid)
    s = S()
    last = int(request.headers.get("last-event-id") or after or 0)

    async def gen():
        nonlocal last
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            evs = s.store.events(tid, last, 300)
            for e in evs:
                last = e["seq"]
                yield f"id: {e['seq']}\nevent: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            if evs:
                idle = 0.0
                continue
            if not follow:
                return
            await asyncio.to_thread(s.store.wait, 1.0)
            idle += 1.0
            if idle >= 15:
                idle = 0.0
                yield ": ping\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ runs --
@app.get("/api/runs")
def runs(thread_id: str | None = None):
    return [{k: r.get(k) for k in ("id", "thread_id", "workflow", "domain", "status", "started", "ended", "summary")}
            for r in S().store.runs(thread_id)]


@app.get("/api/runs/{rid}")
def run(rid: str):
    r = _run(rid)
    s = S()
    return {**r, "artifacts": s.store.artifacts(rid), "verification": s.store.load(rid, "verification")}


@app.get("/api/runs/{rid}/audit")
def audit(rid: str):
    _run(rid)
    return S().store.audits(rid)


@app.get("/api/runs/{rid}/artifacts/{name}")
def artifact(rid: str, name: str):
    _run(rid)
    data = S().store.load(rid, name)
    if data is None:
        raise HTTPException(404, f"产物 {name} 不存在")
    return data


@app.get("/api/runs/{rid}/trace")
def trace(rid: str, focus: str | None = None, cap: int = 400, offset: int = 0):
    _run(rid)
    return views.trace(S().store, rid, focus=focus, cap=max(50, min(cap, 1500)), offset=max(0, offset))


@app.get("/api/runs/{rid}/table/{kind}")
def table(rid: str, kind: str, q: str = "", offset: int = 0, limit: int = 100, status: str = ""):
    _run(rid)
    if kind not in ("rule", "requirement", "scenario", "testcase"):
        raise HTTPException(400, "kind 必须是 rule / requirement / scenario / testcase")
    return views.table(S().store, rid, kind, q, offset, min(limit, 500), status)


@app.get("/api/runs/{rid}/node")
def node(rid: str, id: str):
    """One trace node with its ancestors and direct children (detail panel)."""
    _run(rid)
    tr = views.trace(S().store, rid, full=True)
    nodes = {n["id"]: n for n in tr["nodes"]}
    if id not in nodes:
        raise HTTPException(404, "节点不存在")
    up = [e["source"] for e in tr["edges"] if e["target"] == id and e["kind"] in ("derives", "evolves")]
    down = [e["target"] for e in tr["edges"] if e["source"] == id and e["kind"] in ("derives", "evolves")]
    peers = [{"id": e["target"] if e["source"] == id else e["source"], "kind": e["kind"]} for e in tr["edges"]
             if e["kind"] in ("conflict", "next") and id in (e["source"], e["target"])]
    return {"node": nodes[id], "parents": [nodes[x] for x in up if x in nodes][:20],
            "children": [nodes[x] for x in down if x in nodes][:50], "children_total": len(down),
            "peers": [{**nodes[p["id"]], "relation": p["kind"]} for p in peers if p["id"] in nodes][:20]}


@app.get("/api/runs/{rid}/details")
def details(rid: str):
    """Workflow-specific views: RAFT per-rule pipeline, CARE change set, LLM4Fin conflicts."""
    r = _run(rid)
    s = S().store
    wf = r["workflow"]
    if wf == "raft":
        data = s.load(rid, "raft_rules") or {}
        rows = []
        for x in data.get("rules", []):
            t = x.get("testability") or {}
            rows.append({"rid": x["rid"], "rule": x.get("rule_cn") or x["rule"], "testable": x.get("testable"),
                         "filter_reason": x.get("filter_reason"), "trl": x.get("trl"), "gvr": x.get("gvr"),
                         "testability": {k: t.get(k) for k in ("testable", "violations", "reason", "refined", "override", "history")},
                         "trl_final": x.get("trl_final"), "trl_postprocess": x.get("trl_postprocess"), "parse": x.get("parse"),
                         "tests": sum(len(g) for g in x.get("sub_tests") or [])})
        return {"workflow": wf, "rules": rows, "scenarios": s.load(rid, "raft_scenarios"), "meta_model": s.load(rid, "raft_mm"),
                "representation": (s.load(rid, "raft_rep") or {}).get("representation")}
    if wf == "care":
        d = s.load(rid, "care_diff") or {}
        old, new = s.load(rid, "care_old") or {}, s.load(rid, "care_new") or {}
        return {"workflow": wf, "diff": {k: d.get(k) for k in ("to_delete_rules", "to_add_rules", "modified", "new_map")},
                "impact": s.load(rid, "care_impact"), "update": s.load(rid, "care_update"),
                "old_rules": old.get("rules", []), "new_rules": new.get("rules", []),
                "formalize": {"old": old.get("formalize"), "new": new.get("formalize")},
                "relation_size": len(s.load(rid, "care_relation") or {})}
    if wf == "llm4fin":
        return {"workflow": wf, "conflicts": (s.load(rid, "l4f_conflicts") or {}).get("conflicts", []),
                "sco": (s.load(rid, "l4f_sco") or {}).get("stats")}
    return {"workflow": wf}


@app.get("/api/runs/{rid}/tests")
def tests(rid: str, fmt: str = "json", variant: str = "full"):
    _run(rid)
    store = S().store
    if variant == "min" and store.load(rid, "tests_min"):
        rows = [tc for g in (store.load(rid, "tests_min") or {}).get("testcases", []) for tc in g]
        groups = (store.load(rid, "tests_min") or {}).get("testcases", [])
    else:
        rows = views.tests_flat(store, rid)
        groups = (store.load(rid, "tests") or {}).get("testcases", [])
    if fmt == "csv":
        keys = list(dict.fromkeys(k for tc in rows for k in tc))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="testcases_{rid}_{variant}.csv"'})
    return Response(json.dumps(groups, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="testcases_{rid}_{variant}.json"'})


# ------------------------------------------------------------- knowledge --
@app.get("/api/knowledge")
def knowledge():
    return S().kb.list()


@app.get("/api/knowledge/{domain}")
def knowledge_detail(domain: str):
    p = S().kb.get(domain)
    if not p:
        raise HTTPException(404, "领域知识不存在")
    return p


@app.delete("/api/knowledge/{domain}")
def knowledge_delete(domain: str):
    s = S()
    p = s.kb.get(domain)
    if not p:
        raise HTTPException(404, "领域知识不存在")
    if p.get("source") == "builtin":
        raise HTTPException(400, "内置知识不能删除")
    s.kb.path(domain).unlink()
    return {"deleted": domain}


# ---------------------------------------------------------------- memory --
@app.get("/api/memory")
def memory():
    m = S().memory
    return {"prefs": m.prefs(), "pref_keys": PREF_KEYS, "episodes": m.episodes(None, 50), "docs": m.docs()}


@app.put("/api/memory/prefs/{key}")
async def set_pref(key: str, req: Request):
    if key not in PREF_KEYS:
        raise HTTPException(400, f"未知偏好 {key}")
    body = await req.json()
    S().memory.set_pref(key, body.get("value"), source="ui")
    return S().memory.prefs()


@app.delete("/api/memory/prefs/{key}")
def del_pref(key: str):
    S().memory.forget_pref(key)
    return S().memory.prefs()


# ------------------------------------------------------------------- web --
if (WEB / "vendor").exists():
    app.mount("/vendor", StaticFiles(directory=WEB / "vendor"), name="vendor")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/{name}")
def static(name: str):
    p = WEB / name
    if name in ("app.js", "styles.css", "graphs.js") and p.exists():
        return FileResponse(p)
    raise HTTPException(404)
