"""Pure-function tests: TRL checker, knowledge parsing/consensus, routing, plan building."""
from regtest_agent.agent.graph import _fold_roles, _missing
from regtest_agent.agent.sop import SOP, build_steps, route
from regtest_agent.knowledge import aggregate, consensus, parse_bnf, parse_ocl, parse_puml, parse_symbols
from regtest_agent.tools import trl as T

SYMS = {"Voltage", "Target", "Duration", "Status", "Protection", "Action"}
LABELS = {"电压", "操作对象", "持续时间", "状态", "保护机制"}
RULE = "当光伏发电站并网点电压跌至标称电压的20%且持续625ms时，光伏发电站应保持不脱网连续运行。"


# ----------------------------------------------------------------- TRL --
def test_trl_ok():
    trl = "rule 1\nif Target = 光伏发电站并网点 and Voltage = 20%标称电压 and Duration = 625ms\nthen Status = 不脱网"
    r = T.check(trl, SYMS, LABELS, [RULE])
    assert r["ok"], r


def test_trl_unknown_key_and_ungrounded_value():
    trl = "rule 1\nif Target = 光伏发电站 and Speed = 30\nthen Protection = 持续提供无功支撑"
    r = T.check(trl, SYMS, LABELS, [RULE])
    assert not r["ok"]
    assert any("Speed" in e for e in r["errors"])
    assert any("持续提供无功支撑" in e for e in r["errors"])
    # state/result keys are exempt: their values may come from state machines rather than the rule text
    assert T.check("rule 1\nif Target = 光伏发电站\nthen Status = 未申报", SYMS, LABELS, [RULE])["ok"]


def test_trl_numbers_must_come_from_rule():
    src = [RULE, T.DOC_MARK + "其他条款：1200A 过电流保护"]
    assert T.grounded("625ms", src) and T.grounded("20%", src)
    assert not T.grounded("1200A", src)  # appears only elsewhere in the document
    assert T.grounded("0.2", src)  # 20% == 0.2


def test_trl_bare_multi_if_blocks_and_structure_errors():
    trl = "if Voltage = 20% then Status = 不脱网\nif Voltage = 0 then Status = 不脱网"
    assert len(T.split_rules(trl)) == 2
    bad = T.check("rule 1\nVoltage = 20%", SYMS, LABELS, [RULE])
    assert not bad["ok"] and "if ... then" in bad["errors"][0]


def test_trl_clause_parsing():
    assert T.parse_clause("Quantity % 100 == 0") == ("Quantity", "%", "100==0")
    assert T.parse_clause("Voltage >= 90%") == ("Voltage", ">=", "90%")
    assert T.parse_clause("Action notin 撤销") == ("Action", "notin", "撤销")
    assert T.parse_clause("UsageInstructions CONTAINS 疗效") is None


def test_trl_rejects_undefined_operators_and_multiword_keys():
    for bad in ("rule 1\nif Target IS IN 光伏发电站\nthen Status = 不脱网", "rule 1\nif Target = 光伏发电站\nthen Status = 不脱网 and WITH SOURCE = GB"):
        r = T.check(bad, SYMS, LABELS, [RULE])
        assert not r["ok"], bad


# ----------------------------------------------------------- knowledge --
PUML_A = """@startuml
class Rule
Rule --> Precondition : contains
Precondition --> Actor : contains
Precondition --> Time : contains
Operation --> Action : contains
Operation --> Price : contains
ExpectedResult --> Result : contains
Price ..> Result : constrains
@enduml"""
PUML_B = """```plantuml
@startuml
Rule "1" -- "1" Precondition
Precondition "1" -- "0..*" Actor
Precondition "1" -- "0..*" TimeWindow
Operation o-- Action
Operation o-- Quantity
ExpectedResult ||--o{ Result : contains
@enduml```"""


def test_parse_puml_variants():
    a, b = parse_puml(PUML_A), parse_puml(PUML_B)
    assert a["entities"] == {"Actor": "Precondition", "Time": "Precondition", "Action": "Operation", "Price": "Operation", "Result": "ExpectedResult"}
    assert ("Price", "constrains", "Result") in a["relations"]
    assert b["entities"]["Actor"] == "Precondition" and b["entities"]["Quantity"] == "Operation" and b["entities"]["Result"] == "ExpectedResult"


def test_consensus_k_majority():
    a, b = parse_puml(PUML_A), parse_puml(PUML_B)
    c = {"entities": {"Actor": "Precondition", "Action": "Operation", "Status": "Operation"}, "relations": []}
    mm = consensus([a, b, c], 2)
    assert set(mm["entities"]) == {"Actor", "Action", "Result"}
    assert {"Time", "Price", "Quantity", "Status", "TimeWindow"} <= set(mm["others"]["entities"])
    assert mm["votes"]["Actor"] == 3


REP = """## Symbols
- Domain Symbol
  - Precondition: Actor, TradingInstrument, Time
  - Operation: Action, Quantity
  - ExpectedResult: Result
## Syntax
Rule ::= "IF" <Precondition> "AND" <Operation> "THEN" <ExpectedOutcome>
Comparator ::= "=" | "!=" | ">"
## Testability Constraints
context Rule
inv StructuralCompleteness:
    not self.Precondition.oclIsUndefined()
context Rule
inv ActionExecutable:
    self.Operation.Action.notEmpty()
"""


def test_parse_representation():
    s = parse_symbols(REP)
    assert s == {"Precondition": ["Actor", "TradingInstrument", "Time"], "Operation": ["Action", "Quantity"], "ExpectedResult": ["Result"]}
    assert [r["name"] for r in parse_bnf(REP)] == ["Rule", "Comparator"]
    assert [i["name"] for i in parse_ocl(REP)] == ["StructuralCompleteness", "ActionExecutable"]


def test_parse_symbols_rejects_prose():
    prose = "- Precondition: A logical expression over domain attributes\n| **Domain Symbols** | `ProductName`, `CleaningMethod` | x |"
    s = parse_symbols(prose, {"CleaningMethod": "Operation"})
    assert s == {"Precondition": ["ProductName"], "Operation": ["CleaningMethod"]}


def test_parse_ocl_variants():
    text = """```ocl
-- 1. every rule has a precondition
context Rule
inv: self.precondition->size() > 0

context Rule inv:
  -- C2: action must exist
  Operation.Action->size() >= 1

context DomainSymbol
  self.name in {"A", "B"}
```"""
    o = parse_ocl(text)
    assert [x["context"] for x in o] == ["Rule", "Rule", "DomainSymbol"]
    assert o[0]["note"].startswith("1. every rule") and o[1]["note"].startswith("C2")
    assert o[1]["body"] == "Operation.Action->size() >= 1" and o[2]["body"] == 'self.name in {"A", "B"}'


def test_parse_ocl_bare_fenced_constraints():
    text = """```ocl
-- Constraint 1: language
R.pre.LanguageRequirement = "Chinese"

-- Constraint 2: reusability limit
IF R.Operation CONTAINS "Reuse"
AND R.ExpectedResult NOT CONTAINS "Limit"
→ FAIL  // Violates Rule 9
```
Prose after the fence is ignored."""
    o = parse_ocl(text)
    assert [x["note"] for x in o] == ["Constraint 1: language", "Constraint 2: reusability limit"]
    assert o[1]["body"] == 'IF R.Operation CONTAINS "Reuse" AND R.ExpectedResult NOT CONTAINS "Limit" → FAIL'
    assert all(x["context"] == "Rule" for x in o)


def test_aggregate_union_dedup():
    r1 = {"symbols": {"Precondition": ["Actor"]}, "bnf": [{"name": "Rule", "alternatives": ["a"]}],
          "ocl": [{"context": "Rule", "name": "X", "body": "self.a"}]}
    r2 = {"symbols": {"Precondition": ["Actor", "Time"]}, "bnf": [{"name": "Rule", "alternatives": ["a", "b"]}],
          "ocl": [{"context": "Rule", "name": "X", "body": "self.a "}, {"context": "Rule", "name": "X", "body": "self.b"}]}
    rep = aggregate([r1, r2])
    assert rep["symbols"]["Precondition"] == ["Actor", "Time"]
    assert rep["bnf"][0]["alternatives"] == ["a", "b"]
    assert [o["name"] for o in rep["ocl"]] == ["X", "X2"]


# ------------------------------------------------------------- routing --
def test_route_finance_zh_uses_llm4fin():
    wf, sops, reasons = route("generate_tests", {"domain": "finance", "title": "金融"}, {"found": True, "source": "builtin"}, "zh")
    assert wf == "llm4fin" and sops == ["llm4fin"] and any("LLM4Fin" in r for r in reasons)


def test_route_known_nonfinance_uses_raft_phase2():
    wf, sops, _ = route("generate_tests", {"domain": "power"}, {"found": True, "source": "builtin"}, "zh")
    assert (wf, sops) == ("raft", ["raft_phase2"])


def test_route_unknown_domain_builds_knowledge_first():
    wf, sops, _ = route("generate_tests", {"domain": "medical"}, {"found": False}, "zh")
    assert (wf, sops) == ("raft", ["raft_phase1", "raft_phase2"])


def test_route_reuse_and_build():
    assert route("reuse_tests", {}, {}, "zh")[0] == "care"
    assert route("build_knowledge", {"domain": "x"}, {"found": False}, "zh")[1] == ["raft_phase1"]
    assert route("generate_tests", {"domain": "finance"}, {"found": True}, "en")[0] == "raft"  # mengzi models are Chinese-only


def test_build_steps_follow_sop_order():
    steps = build_steps(["raft_phase1", "raft_phase2"], "zh", {"max_rules": 50})
    tools = [s["tool"] for s in steps]
    assert tools == [t for t, _ in SOP["raft_phase1"]] + [t for t, _ in SOP["raft_phase2"] if t not in ("raft.translate", "tests.minimize")]
    assert next(s for s in steps if s["tool"] == "raft.segment")["args"] == {"max_rules": 50}
    assert "raft.translate" in [s["tool"] for s in build_steps(["raft_phase2"], "en", {})]


# ------------------------------------------------------- minimization --
def test_minimize_gated_opt_in():
    off = [s["tool"] for s in build_steps(["llm4fin"], "zh", {})]
    on = [s["tool"] for s in build_steps(["llm4fin"], "zh", {"minimize": True})]
    assert "tests.minimize" not in off  # full suite stays canonical by default
    assert on[-1] == "tests.minimize"  # appended to the generate phase when enabled


def test_minimize_pairwise_covers_and_keeps_balance():
    from regtest_agent.minimize import minimize, minimize_group
    # a 2-factor cartesian product: 3 methods x 2 directions, each with 成功/不成功 => 12 cases
    group = []
    i = 0
    for m in ("匹配成交", "竞买成交", "询价成交"):
        for d in ("买入", "卖出"):
            for res in ("成功", "不成功"):
                i += 1
                group.append({"rule": "1.1", "testid": f"1.1_{i}", "交易方式": m, "交易方向": d, "结果": res})
    kept, info = minimize_group(group)
    assert info["reason"] == "pairwise"
    # every observed value-pair (method,direction) must still be covered
    want = {(m, d) for m in ("匹配成交", "竞买成交", "询价成交") for d in ("买入", "卖出")}
    got = {(tc["交易方式"], tc["交易方向"]) for tc in kept}
    assert want <= got
    assert {tc["结果"] for tc in kept} == {"成功", "不成功"}  # both outcome classes preserved
    assert len(kept) < len(group)  # actually reduced
    res = minimize([group])
    assert res["before"] == 12 and res["after"] == len(kept) and res["reduction"] > 0


def test_minimize_keeps_small_and_identical_groups():
    from regtest_agent.minimize import minimize_group
    small = [{"rule": "1", "testid": "1_1", "x": "a", "结果": "成功"}]
    assert minimize_group(small)[0] == small  # below min_size kept whole


# ------------------------------------------------------ verify verdict --
def test_verdict_and_explain():
    from regtest_agent.agent import verify as V
    ok = [{"name": "生成测试用例", "ok": True, "level": "error", "detail": ""}]
    assert V.verdict(ok, []) == "pass"
    assert "通过" in V.explain(ok, [], "pass")
    warn = ok + [{"name": "规则覆盖率", "ok": False, "level": "warn", "detail": "50%"}]
    assert V.verdict(warn, []) == "needs_review"
    assert "规则覆盖率" in V.explain(warn, [], "needs_review")
    err = ok + [{"name": "用例可追溯", "ok": False, "level": "error", "detail": ""}]
    assert V.verdict(err, []) == "fail"
    assert "用例可追溯" in V.explain(err, [], "fail")
    # a 'no' judgment on a sample drives needs_review and is named
    bad_review = [{"rule_id": "3.1", "faithful": "no", "tests_consistent": "yes"}]
    assert V.verdict(ok, bad_review) == "needs_review"
    assert "3.1" in V.explain(ok, bad_review, "needs_review")


def test_reuse_roles_and_missing():
    files = [{"id": "a", "name": "交易规则（2021年修订）.pdf"}, {"id": "b", "name": "交易规则（2023年修订）.pdf"}]
    roles = _fold_roles(files, [], "reuse_tests")
    assert roles == {"a": "old_rules", "b": "new_rules"}
    st = {"intent": "reuse_tests", "files": files, "roles": roles}
    assert _missing(st) == ["原测试用例（JSON）"]
    files.append({"id": "c", "name": "testcase.json"})
    st["roles"] = _fold_roles(files, [], "reuse_tests")
    assert _missing(st) == []


# ----------------------------------------------------------- CARE ids --
def test_care_dedup_ids_reused_first():
    from regtest_agent.workers.care import dedup_ids
    a = {"rule": "3.1", "testid": "3.1_1"}  # old 2.1_1 remapped onto 3.1
    b = {"rule": "3.1", "testid": "3.1_1"}  # old 2.2_1 also remapped onto 3.1_1
    new = {"rule": "3.1", "testid": "3.1_1"}  # newly generated, numbered from _1
    final = [[new], [a, b]]
    kept, ren = dedup_ids(final, {id(a): "2.1_1", id(b): "2.2_1"})
    assert kept == {"3.1_1": "2.1_1", "3.1_2": "2.2_1"} and new["testid"] == "3.1_3"
    assert ren == [["3.1_1", "3.1_2"], ["3.1_1", "3.1_3"]]
