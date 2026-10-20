"""Artifact views: rule → requirement → scenario → testcase trace graph, tables and samples,
built from a run's saved step outputs for each workflow."""
from __future__ import annotations

import re
from typing import Any

from .store import Store

MAX_NODES = 1500


def _rid_lineage(rid: str, rule_ids: list[str]) -> str | None:
    best = None
    for c in rule_ids:
        if (rid == c or rid.startswith(c + ".")) and (best is None or len(c) > len(best)):
            best = c
    return best


def _expect(tc: dict) -> str:
    return str(tc.get("结果", tc.get("Result", "")))


def _tc_label(tc: dict) -> str:
    keys = [k for k in tc if k not in ("rule", "testid", "测试关注点", "结果", "结果状态")]
    return "；".join(f"{k}={tc[k]}" for k in keys[:3])


def _parse_dsl(text: str) -> list[dict]:
    """'rule X\\nsourceId..\\nfocus..\\nbefore/after\\n if ..\\n then ..' blocks -> dicts."""
    out, cur = [], None
    for line in (text or "").split("\n"):
        s = line.strip()
        if s.startswith("rule "):
            cur = {"id": s[5:].strip(), "if": "", "then": "", "before": [], "after": []}
            out.append(cur)
        elif cur is None:
            continue
        elif s.startswith("sourceId"):
            cur["source"] = s.split(" ", 1)[-1].strip()
        elif s.startswith("focus:"):
            cur["focus"] = s[6:].strip()
        elif s.startswith("before:"):
            cur["before"] = re.findall(r"'([^']+)'", s) or [x for x in s[7:].strip().split(",") if x]
        elif s.startswith("after:"):
            cur["after"] = re.findall(r"'([^']+)'", s) or [x for x in s[6:].strip().split(",") if x]
        elif s.startswith("if "):
            cur["if"] = s[3:]
        elif s.startswith("then "):
            cur["then"] = s[5:]
    return out


def _json_rules(rs: Any) -> list[dict]:
    rs = rs.get("rules") if isinstance(rs, dict) else rs
    out = []
    for r in rs or []:
        t = r.get("text", "")
        m = re.search(r"if (.*?)\n\s*then (.*)", t, re.S)
        out.append({"id": r["rule"], "source": r.get("sourceId"), "if": m.group(1).strip() if m else "",
                    "then": m.group(2).strip() if m else t.strip(), "before": r.get("before", []), "after": r.get("after", [])})
    return out


class G:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._e = set()

    def node(self, nid: str, type_: str, label: str, **kw) -> str:
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "type": type_, "label": label, **kw}
        else:
            self.nodes[nid].update({k: v for k, v in kw.items() if v is not None})
        return nid

    def edge(self, a: str, b: str, kind: str = "derives") -> None:
        if a in self.nodes and b in self.nodes and (a, b, kind) not in self._e:
            self._e.add((a, b, kind))
            self.edges.append({"source": a, "target": b, "kind": kind})


def _l4f(st: Store, rid: str, g: G) -> None:
    tco = st.load(rid, "l4f_tco") or {}
    for c in tco.get("tci", []):
        g.node(f"rule:{c['id']}", "rule", c["id"], text=c["text"])
    r1 = st.load(rid, "l4f_r1") or {}
    reqs = _parse_dsl(r1.get("r1", ""))
    rule_ids = [c["id"] for c in tco.get("tci", [])]
    req_ids = [q["id"] for q in reqs]
    for q in reqs:
        g.node(f"req:{q['id']}", "requirement", q["id"], text=f"if {q['if']}\nthen {q['then']}", focus=q.get("focus"))
        g.edge(f"rule:{q.get('source') or _rid_lineage(q['id'], rule_ids)}", f"req:{q['id']}")
    r3 = st.load(rid, "l4f_r3") or {}
    scen = _parse_dsl(r3.get("r3", ""))
    for s in scen:
        g.node(f"scn:{s['id']}", "scenario", s["id"], text=f"if {s['if']}\nthen {s['then']}", focus=s.get("focus"), composite="," in s["id"])
        for part in s["id"].split(","):
            q = _rid_lineage(part, req_ids)
            if q:
                g.edge(f"req:{q}", f"scn:{s['id']}")
    for s in scen:
        for b in s.get("after", [])[:6]:
            g.edge(f"scn:{s['id']}", f"scn:{b}", "next")
    _tests(st, rid, g, lambda tc: f"scn:{tc['rule']}")
    conf = st.load(rid, "l4f_conflicts") or {}
    for c in conf.get("conflicts", []):
        ids = c.get("rule_ids", [])
        if len(ids) == 2:
            g.edge(f"req:{ids[0]}", f"req:{ids[1]}", "conflict")


def _tests(st: Store, rid: str, g: G, parent, status=None) -> None:
    t = st.load(rid, "tests") or {}
    for grp in t.get("testcases", []):
        for tc in grp:
            nid = f"tc:{tc['testid']}"
            g.node(nid, "testcase", tc["testid"], expected=_expect(tc), text=_tc_label(tc), data=tc,
                   status=(status(tc) if status else None))
            p = parent(tc)
            if p:
                g.edge(p, nid)


def _raft(st: Store, rid: str, g: G) -> None:
    data = st.load(rid, "raft_rules") or {}
    for r in data.get("rules", []):
        if not r.get("testable") and not r.get("trl"):
            continue
        gvr_failed = (r.get("gvr") or {}).get("status") == "discarded" or not r.get("trl")
        g.node(f"rule:{r['rid']}", "rule", r["rid"], text=r.get("rule_cn") or r["rule"],
               status=None if r.get("trl_final") else "unformalized" if gvr_failed else "discarded")
        trl = r.get("trl_final") or r.get("trl")
        if not trl:
            continue
        tst = r.get("testability") or {}
        g.node(f"req:{r['rid']}", "requirement", f"{r['rid']}·TRL", text=trl,
               status="refined" if tst.get("refined") else "kept" if tst.get("override") == "user_kept" else None)
        g.edge(f"rule:{r['rid']}", f"req:{r['rid']}")
        for j, sub in enumerate(r.get("trl_parsed") or [], 1):
            sid = f"scn:{r['rid']}.{j}"
            cond = " and ".join(" ".join(c) for c in sub.get("conditions", []))
            cons = " and ".join(" ".join(c) for c in sub.get("consequences", []))
            g.node(sid, "scenario", f"{r['rid']}.{j}", text=f"if {cond}\nthen {cons}")
            g.edge(f"req:{r['rid']}", sid)
    sc = st.load(rid, "raft_scenarios") or {}
    for e in sc.get("edges", []):
        g.edge(f"req:{e['from']}", f"req:{e['to']}", "next")
    _tests(st, rid, g, lambda tc: f"scn:{tc['rule']}")


def _care(st: Store, rid: str, g: G) -> None:
    old, new = st.load(rid, "care_old") or {}, st.load(rid, "care_new") or {}
    d = st.load(rid, "care_diff") or {}
    upd = st.load(rid, "care_update") or {}
    imp = st.load(rid, "care_impact") or {}
    rel = st.load(rid, "care_relation") or {}
    deleted_ids = {r["id"] for r in d.get("to_delete_rules", [])}
    added_ids = {r["id"] for r in d.get("to_add_rules", [])}
    modified = set(d.get("modified") or (deleted_ids & added_ids))  # same id deleted + re-added = modified
    hit_scn = set(imp.get("to_delete_scenarios", []))
    for side, src in (("old", old), ("new", new)):
        if not src:
            continue
        tag = "原" if side == "old" else "新"
        for r in src.get("rules", []):
            if side == "old":
                status = "modified" if r["id"] in modified else "deleted" if r["id"] in deleted_ids else "unchanged"
            else:
                status = "modified" if r["id"] in modified else "added" if r["id"] in added_ids else "unchanged"
            g.node(f"{side}:rule:{r['id']}", "rule", f"{tag}·{r['id']}", text=r["text"], side=side, status=status)
        reqs = _json_rules(src.get("requirements"))
        rule_ids = [r["id"] for r in src.get("rules", [])]
        for q in reqs:
            g.node(f"{side}:req:{q['id']}", "requirement", f"{tag}·{q['id']}", text=f"if {q['if']}\nthen {q['then']}", side=side)
            g.edge(f"{side}:rule:{q.get('source') or _rid_lineage(q['id'], rule_ids)}", f"{side}:req:{q['id']}")
        req_ids = [q["id"] for q in reqs]
        for s in _json_rules(src.get("scenarios")):
            st_ = "affected" if side == "old" and s["id"] in hit_scn else None
            g.node(f"{side}:scn:{s['id']}", "scenario", f"{tag}·{s['id']}", text=f"if {s['if']}\nthen {s['then']}", side=side, status=st_)
            q = _rid_lineage(s["id"], req_ids)
            if q:
                g.edge(f"{side}:req:{q}", f"{side}:scn:{s['id']}")
    for r in old.get("rules", []):
        if r["id"] in {x["id"] for x in new.get("rules", [])}:
            g.edge(f"old:rule:{r['id']}", f"new:rule:{r['id']}", "evolves")
    old_tests = st.load(rid, "tests_old") or {}
    reused = upd.get("reused", {})
    deleted = set(upd.get("deleted", []))
    old_id_to_rules = {}
    for rule_id, tids in rel.items():
        for t in tids:
            old_id_to_rules.setdefault(t, []).append(rule_id)
    for grp in old_tests.get("testcases", []):
        for tc in grp:
            if tc["testid"] in deleted:
                nid = g.node(f"old:tc:{tc['testid']}", "testcase", tc["testid"], expected=_expect(tc), text=_tc_label(tc),
                             data=tc, side="old", status="deleted")
                for r in old_id_to_rules.get(tc["testid"], [])[:3]:
                    g.edge(f"old:rule:{r}", nid)
    new_scn = {n["label"].split("·", 1)[-1] for n in g.nodes.values() if n.get("side") == "new" and n["type"] == "scenario"}
    new_rules = [r["id"] for r in new.get("rules", [])]

    def status(tc):
        o = reused.get(tc["testid"])
        if o is None:
            return "added"
        return "remapped" if o != tc["testid"] else "reused"

    def parent(tc):
        if tc["rule"] in new_scn:
            return f"new:scn:{tc['rule']}"
        r = _rid_lineage(tc["rule"], new_rules)
        if r:
            return f"new:rule:{r}"
        o = reused.get(tc["testid"])
        rs = old_id_to_rules.get(o or "", [])
        if rs:
            return f"old:rule:{rs[0]}"
        if o:  # reused verbatim; its rule was not part of the processed (changed) scope
            rid_ = ".".join(tc["rule"].split(",")[0].split(".")[:3])
            return g.node(f"out:rule:{rid_}", "rule", f"范围外·{rid_}", text="该规则不在本次 CARE 处理范围内（未识别为变更），其原测试用例按原样复用",
                          status="unchanged", virtual=True)
        return None

    t = st.load(rid, "tests") or {}
    for grp in t.get("testcases", []):
        for tc in grp:
            nid = g.node(f"tc:{tc['testid']}", "testcase", tc["testid"], expected=_expect(tc), text=_tc_label(tc), data=tc,
                         status=status(tc), origin=reused.get(tc["testid"]))
            p = parent(tc)
            if p:
                g.edge(p, nid)


def trace(st: Store, rid: str, full: bool = False, focus: str | None = None, cap: int = 400, offset: int = 0) -> dict:
    run = st.run(rid) or {}
    wf = run.get("workflow", "")
    g = G()
    if wf == "llm4fin":
        _l4f(st, rid, g)
    elif wf == "raft":
        _raft(st, rid, g)
    elif wf == "care":
        _care(st, rid, g)
    nodes, edges = list(g.nodes.values()), g.edges
    stats = {}
    for n in nodes:
        if not n.get("virtual"):
            stats[n["type"]] = stats.get(n["type"], 0) + 1
    status = {}
    for n in nodes:
        if n.get("status") and not n.get("virtual"):
            k = f"{n['type']}:{n['status']}"
            status[k] = status.get(k, 0) + 1
    out = {"workflow": wf, "stats": stats, "status": status, "total_nodes": len(nodes), "total_edges": len(edges)}
    if full:
        return {**out, "nodes": nodes, "edges": edges}
    expand = bool(focus and focus.startswith("tcg:"))  # explicit expansion of a folded test group
    if expand:
        focus = focus[4:]
    page = None
    if focus:
        keep = _neighborhood(focus, edges, min(cap * 3, MAX_NODES))
        keep |= {e["target"] if e["source"] == focus else e["source"] for e in edges  # conflicting / chained peers
                 if e["kind"] in ("conflict", "next") and focus in (e["source"], e["target"])}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        # a rule/requirement can fan out to hundreds of tests: fold them per scenario, expanded by focusing the scenario
        folded = (not expand and (g.nodes.get(focus) or {}).get("type") in ("rule", "requirement")
                  and sum(n["type"] == "testcase" for n in nodes) > 60)
        if folded:
            nodes, edges = _collapse_tests(nodes, edges)
    else:  # overview: test cases folded into one group node per parent, rules shown batch by batch
        nodes, edges = _collapse_tests(nodes, edges)
        keep, page = _sample(nodes, edges, cap, offset)
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        folded = True
    nodes = [dict(n, data=None) if n["type"] != "testcase" else n for n in nodes]
    return {**out, "nodes": nodes, "edges": edges, "truncated": len(nodes) < out["total_nodes"], "collapsed": folded,
            "mode": "focus" if focus else "overview", "page": page}


def _collapse_tests(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    tc = {n["id"]: n for n in nodes if n["type"] == "testcase"}
    parent = {}
    for e in edges:
        if e["target"] in tc and e["kind"] == "derives":
            parent.setdefault(e["target"], e["source"])
    groups: dict[str, dict] = {}
    for tid, n in tc.items():
        g = groups.setdefault(parent.get(tid, ""), {"n": 0, "pos": 0, "status": {}})
        g["n"] += 1
        g["pos"] += _expect(n.get("data") or {}) in ("成功", "可以", "Success", "success")
        s = n.get("status") or "none"
        g["status"][s] = g["status"].get(s, 0) + 1
    out_nodes = [n for n in nodes if n["type"] != "testcase"]
    out_edges = [e for e in edges if e["source"] not in tc and e["target"] not in tc]
    for p, g in groups.items():
        if not p:
            continue
        top = max(g["status"], key=g["status"].get)
        out_nodes.append({"id": f"tcg:{p}", "type": "testgroup", "label": f"用例×{g['n']}", "count": g["n"], "positive": g["pos"],
                          "breakdown": g["status"], "status": None if top == "none" else top, "of": p})
        out_edges.append({"source": p, "target": f"tcg:{p}", "kind": "derives"})
    return out_nodes, out_edges


def _neighborhood(nid: str, edges: list[dict], cap: int) -> set:
    """Ancestors of the focus node plus its descendants (not ancestors of descendants)."""
    up, down = {}, {}
    for e in edges:
        if e["kind"] in ("derives", "evolves"):
            down.setdefault(e["source"], []).append(e["target"])
            up.setdefault(e["target"], []).append(e["source"])
    keep = {nid}
    for nbr in (up, down):
        stack = [nid]
        while stack:
            x = stack.pop()
            for y in nbr.get(x, []):
                if y not in keep and len(keep) < cap:
                    keep.add(y)
                    stack.append(y)
    return keep


def _sample(nodes: list[dict], edges: list[dict], cap: int, offset: int = 0) -> tuple[set, dict]:
    """One batch of rule branches (changed rules first; old/new versions of a rule kept adjacent), starting at
    rule index `offset`, until `cap` nodes. Returns (node ids, page info)."""
    down = {}
    for e in edges:
        if e["kind"] == "derives":
            down.setdefault(e["source"], []).append(e["target"])
    roots = [n["id"] for n in nodes if n["type"] == "rule"]
    changed = {n["id"] for n in nodes if n["type"] == "rule" and n.get("status") not in (None, "unchanged")}
    key = lambda nid: nid.split("rule:", 1)[-1]  # noqa: E731
    same: dict[str, list[str]] = {}
    for r in roots:
        same.setdefault(key(r), []).append(r)
    order = [x for k in dict.fromkeys(key(r) for r in [r for r in roots if r in changed] + roots) for x in same[k]]
    other = {n["id"] for n in nodes if n["type"] != "rule"}
    keep, i = set(), offset
    if len(other) + len(roots) <= cap and offset == 0:
        keep, i = {n["id"] for n in nodes}, len(order)
    while i < len(order):
        branch, stack = {order[i]}, [order[i]]
        while stack and len(branch) < 40:
            x = stack.pop()
            for y in down.get(x, [])[:6]:
                if y not in branch:
                    branch.add(y)
                    stack.append(y)
        if keep and len(keep | branch) > cap:
            break
        keep |= branch
        i += 1
    return keep, {"offset": offset, "end": i, "rules": len(order), "next": i if i < len(order) else None}


def samples(st: Store, rid: str, workflow: str, per_rule: int = 3, per_req: int = 3) -> list[dict]:
    """rule text + up to per_rule requirements, each paired with its own descendant tests, for the LLM judge."""
    out = []
    tr = trace(st, rid, full=True)
    nodes = {n["id"]: n for n in tr["nodes"]}
    down = {}
    for e in tr["edges"]:
        if e["kind"] == "derives":
            down.setdefault(e["source"], []).append(e["target"])
    for n in tr["nodes"]:
        if n["type"] != "rule" or n.get("status") in ("deleted", "discarded", "unformalized") or n.get("side") == "old" or n.get("virtual"):
            continue
        reqs = [nodes[x] for x in down.get(n["id"], []) if nodes[x]["type"] == "requirement"][:per_rule]
        tests = []
        for r in reqs:
            queue, seen, got = list(down.get(r["id"], [])), set(), 0
            while queue and got < per_req:
                y = queue.pop(0)
                if y in seen or nodes[y].get("status") == "deleted":
                    continue
                seen.add(y)
                if nodes[y]["type"] == "testcase":
                    tests.append({"对应需求": r["label"], **{k: v for k, v in (nodes[y].get("data") or {}).items() if k not in ("rule", "testid")}})
                    got += 1
                else:
                    queue.extend(down.get(y, []))
        if tests:
            out.append({"rule_id": n["label"], "rule": n.get("text", ""),
                        "requirement": "\n".join(f"[{r['label']}] {r['text']}" for r in reqs), "tests": tests})
    return out


def table(st: Store, rid: str, kind: str, q: str = "", offset: int = 0, limit: int = 100, status: str = "") -> dict:
    tr = trace(st, rid, full=True)
    rows = [n for n in tr["nodes"] if n["type"] == kind and not n.get("virtual")]
    if q:
        rows = [n for n in rows if q in (n.get("text") or "") or q in n["label"]]
    if status:
        rows = [n for n in rows if (n.get("status") or "") == status]
    if kind == "testcase":
        rows.sort(key=lambda n: n.get("status") == "deleted")  # current tests first, retired ones last
    total = len(rows)
    rows = rows[offset:offset + limit]
    return {"total": total, "rows": rows}


def tests_flat(st: Store, rid: str) -> list[dict]:
    t = st.load(rid, "tests") or {}
    return [tc for g in t.get("testcases", []) for tc in g]
