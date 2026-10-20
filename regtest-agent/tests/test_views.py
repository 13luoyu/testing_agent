"""Trace views built from saved step outputs (synthetic artifacts; no workers / LLM)."""
from regtest_agent import views
from regtest_agent.store import Store


def _run(st: Store, wf: str) -> str:
    rid = st.create_run(st.create_thread()["id"], wf, "d", {})
    return rid


def test_llm4fin_cascade():
    st = Store()
    rid = _run(st, "llm4fin")
    st.save(rid, "l4f_tco", {"tci": [{"id": "3.1.1", "text": "债券现券交易申报数量应当为10万元面额或其整数倍。"}]})
    st.save(rid, "l4f_r1", {"r1": "rule 3.1.1.1\nsourceId 3.1.1\nfocus: 数量\n\tif 操作 is 申报 and 数量 is 100000\n\tthen 结果 is 成功\n"})
    st.save(rid, "l4f_r3", {"r3": "rule 3.1.1.1.1\nfocus: 数量\nbefore: \nafter: \n\tif 操作 is 申报\n\tthen 结果 is 成功\n"})
    st.save(rid, "tests", {"testcases": [[{"rule": "3.1.1.1.1", "testid": "3.1.1.1.1_1", "数量": "100000", "结果": "成功"},
                                          {"rule": "3.1.1.1.1", "testid": "3.1.1.1.1_2", "数量": "99999", "结果": "失败"}]]})
    tr = views.trace(st, rid, full=True)
    assert tr["stats"] == {"rule": 1, "requirement": 1, "scenario": 1, "testcase": 2}
    edges = {(e["source"], e["target"]) for e in tr["edges"]}
    assert ("rule:3.1.1", "req:3.1.1.1") in edges and ("req:3.1.1.1", "scn:3.1.1.1.1") in edges
    assert ("scn:3.1.1.1.1", "tc:3.1.1.1.1_2") in edges
    focus = views.trace(st, rid, focus="tc:3.1.1.1.1_1")
    assert {n["id"] for n in focus["nodes"]} == {"rule:3.1.1", "req:3.1.1.1", "scn:3.1.1.1.1", "tc:3.1.1.1.1_1"}
    s = views.samples(st, rid, "llm4fin")
    assert s and s[0]["rule_id"] == "3.1.1" and len(s[0]["tests"]) == 2
    assert s[0]["requirement"].startswith("[3.1.1.1] if") and all(t["对应需求"] == "3.1.1.1" for t in s[0]["tests"])


def test_raft_cascade_marks_discarded_and_refined():
    st = Store()
    rid = _run(st, "raft")
    st.save(rid, "raft_rules", {"rules": [
        {"rid": "R1", "rule": "a", "rule_cn": "规则一", "testable": True, "trl": "if A = 1 then Result = Success", "trl_final": "if A = 1 then Result = Success",
         "testability": {"testable": True, "refined": True},
         "trl_parsed": [{"conditions": [["A", "=", "1"]], "consequences": [["结果", "=", "成功"]]}]},
        {"rid": "R2", "rule": "b", "rule_cn": "规则二", "testable": True, "trl": "if B = 2 then Result = Success", "testability": {"testable": False}},
        {"rid": "R3", "rule": "标题", "rule_cn": "标题", "testable": False},
        {"rid": "R4", "rule": "d", "rule_cn": "规则四", "testable": True, "trl": "", "gvr": {"status": "discarded", "attempts": 4}},
        {"rid": "R5", "rule": "e", "rule_cn": "规则五", "testable": True, "trl": "if E = 5 then Result = Success", "trl_final": "if E = 5 then Result = Success",
         "testability": {"testable": False, "override": "user_kept"}}]})
    st.save(rid, "tests", {"testcases": [[{"rule": "R1.1", "testid": "R1.1_1", "A": "1", "结果": "成功"}]]})
    tr = views.trace(st, rid, full=True)
    nodes = {n["id"]: n for n in tr["nodes"]}
    assert "rule:R3" not in nodes  # filtered as non-requirement
    assert nodes["rule:R2"]["status"] == "discarded" and nodes["req:R1"]["status"] == "refined"
    assert nodes["rule:R4"]["status"] == "unformalized" and nodes["req:R5"]["status"] == "kept"
    assert {(e["source"], e["target"]) for e in tr["edges"]} >= {("rule:R1", "req:R1"), ("req:R1", "scn:R1.1"), ("scn:R1.1", "tc:R1.1_1")}


def test_care_statuses():
    st = Store()
    rid = _run(st, "care")
    rule = lambda i, t: {"id": i, "text": t}  # noqa: E731
    st.save(rid, "care_old", {"rules": [rule("3.1", "旧一"), rule("3.2", "旧二")], "requirements": [], "scenarios": []})
    st.save(rid, "care_new", {"rules": [rule("3.1", "新一"), rule("3.3", "新三")], "requirements": [], "scenarios": []})
    st.save(rid, "care_diff", {"to_delete_rules": [rule("3.1", "旧一"), rule("3.2", "旧二")], "to_add_rules": [rule("3.1", "新一"), rule("3.3", "新三")], "new_map": {}})
    st.save(rid, "care_relation", {"3.1": ["3.1_1"], "3.2": ["3.2_1"]})
    st.save(rid, "care_update", {"reused": {"3.1_1": "3.1_1"}, "deleted": ["3.2_1"]})
    st.save(rid, "tests_old", {"testcases": [[{"rule": "3.1", "testid": "3.1_1", "结果": "成功"}], [{"rule": "3.2", "testid": "3.2_1", "结果": "成功"}]]})
    st.save(rid, "tests", {"testcases": [[{"rule": "3.1", "testid": "3.1_1", "结果": "成功"}], [{"rule": "3.3", "testid": "3.3_1", "结果": "失败"}]]})
    tr = views.trace(st, rid, full=True)
    n = {x["id"]: x for x in tr["nodes"]}
    assert n["old:rule:3.1"]["status"] == "modified" and n["old:rule:3.2"]["status"] == "deleted" and n["new:rule:3.3"]["status"] == "added"
    assert n["tc:3.1_1"]["status"] == "reused" and n["tc:3.3_1"]["status"] == "added" and n["old:tc:3.2_1"]["status"] == "deleted"
    assert ("old:rule:3.1", "new:rule:3.1") in {(e["source"], e["target"]) for e in tr["edges"]}


def test_overview_pages_rules_and_expands_groups():
    st = Store()
    rid = _run(st, "llm4fin")
    ids = [f"3.{i}" for i in range(1, 7)]
    st.save(rid, "l4f_tco", {"tci": [{"id": i, "text": f"规则{i}"} for i in ids]})
    st.save(rid, "l4f_r1", {"r1": "".join(f"rule {i}.1\nsourceId {i}\n\tif 操作 is 申报\n\tthen 结果 is 成功\n" for i in ids)})
    st.save(rid, "l4f_r3", {"r3": "".join(f"rule {i}.1.1\n\tif 操作 is 申报\n\tthen 结果 is 成功\n" for i in ids)})
    st.save(rid, "tests", {"testcases": [[{"rule": f"{i}.1.1", "testid": f"{i}.1.1_{k}", "结果": "成功" if k % 2 else "不成功"} for k in range(1, 4)] for i in ids]})
    first = views.trace(st, rid, cap=8)
    assert first["mode"] == "overview" and first["page"] == {"offset": 0, "end": 2, "rules": 6, "next": 2}
    assert {n["type"] for n in first["nodes"]} == {"rule", "requirement", "scenario", "testgroup"}
    second = views.trace(st, rid, cap=8, offset=2)
    assert second["page"]["offset"] == 2 and {n["id"] for n in second["nodes"]}.isdisjoint({n["id"] for n in first["nodes"]})
    g = views.trace(st, rid, focus="tcg:scn:3.1.1.1")
    assert sum(n["type"] == "testcase" for n in g["nodes"]) == 3 and not g["collapsed"]


def test_focus_includes_conflicting_requirement():
    st = Store()
    rid = _run(st, "llm4fin")
    st.save(rid, "l4f_tco", {"tci": [{"id": "3.1", "text": "甲"}, {"id": "3.2", "text": "乙"}]})
    st.save(rid, "l4f_r1", {"r1": "rule 3.1.1\nsourceId 3.1\n\tif 数量 is 1\n\tthen 结果 is 成功\nrule 3.2.1\nsourceId 3.2\n\tif 数量 is 2\n\tthen 结果 is 成功\n"})
    st.save(rid, "l4f_conflicts", {"conflicts": [{"rule_ids": ["3.1.1", "3.2.1"], "reason": "x"}]})
    f = views.trace(st, rid, focus="req:3.1.1")
    assert {n["id"] for n in f["nodes"]} == {"rule:3.1", "req:3.1.1", "req:3.2.1"}
    assert {"source": "req:3.1.1", "target": "req:3.2.1", "kind": "conflict"} in f["edges"]


def test_delete_thread_removes_run_artifacts():
    st = Store()
    tid = st.create_thread()["id"]
    rid = st.create_run(tid, "raft", "d", {})
    st.save(rid, "tests", {"testcases": []})
    d = st.s.runs_dir / rid
    assert d.exists()
    st.delete_thread(tid)
    assert not d.exists() and st.run(rid) is None
