"""Domain knowledge packs + RAFT Phase-I consolidation (K-consensus purification for the
meta-model M, union aggregation for representation R and testability constraints T)."""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .config import Settings, get_settings

LAYERS = ("Precondition", "Operation", "ExpectedResult")
CORE = {"Rule", *LAYERS}
# RAFT testability/prompt/judge_testability_step{1..5}: one OCL invariant per step
TESTABILITY_STEPS = ("StructuralCompleteness", "RuleElementDeterministic", "ActionExecutable", "ExpectedResultObservable", "DeterministicOutcome")
CN = {"Actor": "操作主体", "Operator": "操作人", "Target": "操作对象", "Action": "操作", "Time": "时间", "Event": "事件",
      "Constraint": "约束", "Status": "状态", "ResultStatus": "结果状态", "Result": "结果", "Outcome": "结果",
      "TradingInstrument": "交易品种", "TradingMarket": "交易市场", "TradingDirection": "交易方向", "TradingMethod": "交易方式",
      "Quantity": "数量", "Price": "价格", "OperationPart": "操作部分", "VehicleType": "车辆类型", "Condition": "条件",
      "Location": "地点", "Credential": "凭证", "Speed": "速度", "Distance": "距离", "Amount": "金额", "Direction": "方向",
      "Voltage": "电压", "Frequency": "频率", "Fault": "故障类型", "Protection": "保护机制", "Harmonic": "谐波",
      "Flicker": "电压闪变", "PredictionAccuracy": "预测精度", "PowerResponse": "功率响应", "Duration": "持续时间"}
SYN = {"Operator": "Actor", "Subject": "Actor", "Object": "Target", "OperationTarget": "Target", "TestTarget": "Target",
       "Outcome": "Result", "ExpectedOutcome": "Result", "TimeDuration": "Duration", "TestDuration": "Duration",
       "Certificate": "Credential", "VehicleCategory": "VehicleType", "TestAction": "Action", "FaultType": "Fault",
       "VoltageValue": "Voltage", "VoltageLevel": "Voltage", "FrequencyValue": "Frequency", "FrequencyLevel": "Frequency",
       "OperationStatus": "Status", "HarmonicContent": "Harmonic", "FlickerValue": "Flicker", "ProtectionAction": "Protection",
       "PowerPredictionAccuracy": "PredictionAccuracy", "ActivePowerResponse": "PowerResponse", "ResponseCharacteristic": "PowerResponse",
       "FineAmount": "Amount", "PenaltyAmount": "Amount"}

DOMAINS = {
    "finance": {"title": "金融（证券交易）", "kw": ["证券", "交易所", "债券", "基金", "股票", "申报", "回购", "融资融券", "期权", "交易规则", "做市", "结算", "stock", "bond", "exchange", "trading"]},
    "traffic": {"title": "道路交通", "kw": ["道路", "交通", "车辆", "驾驶", "机动车", "行人", "车道", "限速", "高速公路", "信号灯", "vehicle", "driver", "traffic", "speed limit", "pedestrian"]},
    "power": {"title": "电力（新能源并网）", "kw": ["电网", "并网", "光伏", "电站", "电压", "频率", "功率", "发电", "逆变器", "谐波", "低电压穿越", "风电", "grid", "voltage", "frequency", "generating", "photovoltaic"]},
}


def canon(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9]", "", name or "")
    if not n:
        return name.strip()
    n = n[0].upper() + n[1:]
    return SYN.get(n, n)


VERBS = ("contains", "constrains", "dependsOn", "triggers", "depends", "includes", "has")
_REL = re.compile(r'^\s*([A-Za-z_]\w*)\s*(?:"[^"]*"\s*)?(?:([<o*|}{]*[-.]+(?:\w+[-.]+)?[>o*|}{]*)|(' + "|".join(VERBS) + r'))\s*'
                  r'(?:"[^"]*"\s*)?([A-Za-z_]\w*)\s*(?::\s*([A-Za-z_][\w ]*))?', re.M)


def parse_puml(text: str) -> dict:
    """PlantUML meta-model -> {entities: {leaf: layer}, relations: [(a, rel, b)]}. Accepts the variants
    models emit: `A --> B : rel`, `A "1" -- "0..*" B`, `A o-- B`, `A ..> B`, and bare `A contains B`.
    Only leaves attached to a middle-layer node become entities (RAFT's tree constraint)."""
    m = re.search(r"@startuml(.*?)@enduml", text, re.S | re.I)
    src = m.group(1) if m else text
    src = re.sub(r"\s+(?=[A-Z]\w*\s*(?:\"[^\"]*\"\s*)?[-.]+>)", "\n", src)  # one-line dumps
    ents, rels = {}, []
    for a, arrow, verb, b, label in _REL.findall(src):
        if b[0].islower() or a[0].islower():  # e.g. `X "1" -- "1" contains` (verb in class position)
            continue
        rel = (label or verb).strip().split()[0] if (label or verb) else ""
        ca, cb = canon(a), canon(b)
        if cb in LAYERS and ca not in CORE:  # reversed composition: Leaf --* Layer
            ca, cb = cb, ca
        if not rel:
            rel = "contains" if ca in CORE or any(c in arrow for c in "o*") else "depends" if "." in arrow else "relates"
        rel = rel[0].lower() + rel[1:]
        rels.append((ca, rel, cb))
        if ca in LAYERS and cb not in CORE and rel == "contains":
            ents.setdefault(cb, ca)
    return {"entities": ents, "relations": sorted(set(rels))}


_STOP = {x.lower() for x in ("A", "An", "And", "Or", "Not", "If", "Then", "Is", "Be", "Must", "Of", "Set", "Over", "That", "True", "False",
                             "Before", "After", "The", "In", "To", "With", "For", "By", "On", "As", "At", "Null", "Undefined", "None",
                             "Value", "Values", "String", "Number", "Integer", "Date", "Boolean", "Domain", "Symbol", "Symbols", "Logical",
                             "Comparison", "Expression", "Expressions", "Element", "Elements", "Identifier", "Others")}
_ID = re.compile(r"[A-Z][A-Za-z0-9_]{1,40}")
_OPS_RULE = re.compile(r"(Logical|Comparison|Comparator|Operator$|Literal|Bool|Rule$)")


def _ident_list(s: str) -> list[str] | None:
    """'A, B, C' (optionally backticked/quoted) -> identifiers; None when the text is prose."""
    items = [x.strip().strip("`\"'*").strip() for x in re.split(r"[,，、]", s) if x.strip()]
    return items if items and all(_ID.fullmatch(x) for x in items) else None


def _guess_layer(x: str) -> str:
    if re.search(r"(Result|Outcome|Response|Claim|Content|Warning|Accuracy|Harmonic|Flicker|Protection|Effect)", x):
        return "ExpectedResult"
    if re.search(r"(Action|Method|Procedure|Protocol|Operation|Instruction|Fault|Duration|Direction|Quantity|Price|Part)", x):
        return "Operation"
    return "Precondition"


def parse_symbols(text: str, layers: dict | None = None) -> dict:
    """Domain symbols of a representation, accepting only identifier lists: RAFT's '- Precondition: A, B'
    lines, BNF productions whose alternatives are all quoted identifiers, and backticked 'Domain Symbols'
    rows. Symbols without a stated layer go to their meta-model layer (`layers`) or a name-based guess."""
    out: dict[str, list[str]] = {}
    loose: list[str] = []

    def add(layer: str | None, xs: list[str]) -> None:
        for x in xs:
            c = canon(x)
            if not c or c.lower() in _STOP or c in CORE:
                continue
            if layer is None:
                loose.append(c)
            elif c not in out.setdefault(layer, []):
                out[layer].append(c)

    for layer in LAYERS:
        for m in re.finditer(rf"^[\s\-*|]*\**{layer}[^:：\n|]{{0,20}}[:：|]\s*(.+)$", text, re.M):
            xs = _ident_list(m.group(1).strip().strip("|").strip())
            if xs:
                add(layer, xs)
        # header line followed by a bulleted list of `Symbol` items
        for m in re.finditer(rf"^[\s\-*]*\**{layer}\**\s*[:：]?\s*\**\s*\n((?:[ \t]+[-*]\s*`[A-Z]\w*`.*\n?)+)", text, re.M):
            add(layer, re.findall(r"^[ \t]+[-*]\s*`([A-Z]\w*)`", m.group(1), re.M))
    for m in re.finditer(r"^\s*<?([A-Za-z][A-Za-z0-9_]*)>?\s*::=\s*(.+(?:\n\s*\|.+)*)", text, re.M):
        name, body = m.group(1), m.group(2)
        if _OPS_RULE.search(name):
            continue
        for seg in body.split("\n"):  # `"A" | "B"  // Operation` comments name the layer per line
            c = re.search(r"//\s*(Precondition|Operation|ExpectedResult)", seg)
            alts = [a.strip() for a in re.sub(r"//.*$", "", seg).strip().lstrip("|").split("|") if a.strip()]
            if alts and all(re.fullmatch(r"[\"'][A-Z][A-Za-z0-9_]{1,40}[\"']", a) for a in alts) and (c or len(alts) >= 2):
                layer = c.group(1) if c else next((l for l in LAYERS if name.startswith(l[:6])), None) or \
                    ("ExpectedResult" if name.startswith(("Result", "Outcome", "Expected")) else None)
                add(layer, [a.strip("\"'") for a in alts])
    for line in text.split("\n"):
        if re.search(r"Domain Symbol|领域符号", line, re.I):
            add(None, re.findall(r"`([A-Z][A-Za-z0-9_]{1,40})`", line))
    for x in loose:
        if not any(x in v for v in out.values()):
            out.setdefault((layers or {}).get(x) or _guess_layer(x), []).append(x)
    return out


def split_sections(text: str) -> dict:
    """Split a representation document into symbols / syntax / constraints text blocks."""
    t = text
    def grab(pat_start: str, pats_end: list[str]) -> str:
        m = re.search(pat_start, t, re.I)
        if not m:
            return ""
        rest = t[m.end():]
        ends = [x.start() for p in pats_end for x in [re.search(p, rest, re.I)] if x]
        return rest[:min(ends)].strip() if ends else rest.strip()
    sym = grab(r"#+\s*(\d+\.\s*)?(Symbols?|符号)", [r"\n#+\s*(\d+\.\s*)?(Syntax|语法)"])
    syn = grab(r"#+\s*(\d+\.\s*)?(Syntax|语法)", [r"\n#+\s*(\d+\.\s*)?(Semantics|语义|Testability|可测试性)"])
    con = grab(r"#+\s*(\d+\.\s*)?(Testability Constraints|可测试性约束)", [r"\n#+\s*(\d+\.\s*)?(TRL 的完整定义|Complete|完整定义|示例|Example|一个示例)"])
    return {"symbols": sym, "syntax": syn, "constraints": con}


def parse_bnf(text: str) -> list[dict]:
    rules = []
    for m in re.finditer(r"^\s*<?([A-Za-z][A-Za-z0-9_]*)>?\s*::=\s*(.+(?:\n\s*\|.+)*)", text, re.M):
        alts = [re.sub(r"\s+", " ", a).strip() for a in re.split(r"\n\s*\||(?<!\")\|(?!\")", m.group(2)) if a.strip()]
        rules.append({"name": m.group(1), "alternatives": alts})
    return rules


def parse_ocl(text: str) -> list[dict]:
    """OCL invariants. Line scanner: `context X` sets the context, each `inv [Name]:` (or a bare body directly
    under `context X`, or any body inside an ```ocl fence) starts an invariant; the preceding `-- comment`
    becomes its description."""
    invs: list[dict] = []
    names: Counter = Counter()
    ctx, cur, note, fence = None, None, "", ""

    def close():
        nonlocal cur
        if cur and cur["body"].strip():
            body = re.sub(r"\s+", " ", cur["body"]).strip()
            name = cur["name"] or _inv_name(body + " " + cur["note"])
            names[name] += 1
            invs.append({"context": cur["context"], "name": name if names[name] == 1 else f"{name}{names[name]}", "body": body,
                         **({"note": cur["note"]} if cur["note"] else {})})
        cur = None

    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("```"):
            fence = "" if fence else (line[3:].strip().lower() or "code")
        if line.startswith("```") or re.match(r"^#{1,6}\s", line) or (not line and cur and cur["body"]):
            close()
            if line.startswith("#"):
                ctx = None
            continue
        if line.startswith("--"):
            if cur is not None and not cur["body"].strip():  # `context Rule inv:` then `-- C1: ...` then body
                cur["note"] = line.lstrip("-").strip()[:160]
                continue
            close()
            note = line.lstrip("-").strip()[:160]
            continue
        m = re.match(r"^context\s+([A-Za-z_]\w*)(?:\s*::\s*\w+)?\s*(.*)$", line)
        if m:
            close()
            ctx, rest = m.group(1), m.group(2).strip()
            m2 = re.match(r"^inv\s*([A-Za-z_]\w*)?\s*:\s*(.*)$", rest)
            if m2:
                cur = {"context": ctx, "name": m2.group(1) or "", "body": m2.group(2), "note": note}
            elif rest:
                cur = {"context": ctx, "name": "", "body": rest, "note": note}
            else:
                cur = {"context": ctx, "name": "", "body": "", "note": note}
            note = ""
            continue
        m = re.match(r"^inv\s*([A-Za-z_]\w*)?\s*:\s*(.*)$", line)
        if m and ctx:
            pending = note or (cur["note"] if cur is not None and not cur["body"].strip() else "")
            close()
            cur = {"context": ctx, "name": m.group(1) or "", "body": m.group(2), "note": pending}
            note = ""
            continue
        if cur is not None and line and not line.startswith(("|", ">", "*")):
            cur["body"] += " " + re.split(r"--|//", line)[0]
        elif cur is None and line and fence == "ocl":  # `-- Constraint N: ...` followed by a bare body
            cur = {"context": ctx or "Rule", "name": "", "body": re.split(r"--|//", line)[0], "note": note}
            note = ""
    close()
    return invs


def _inv_name(body: str) -> str:
    b = body.lower()
    for k, n in (("precondition", "StructuralCompleteness"), ("executable", "ActionExecutable"), ("observable", "ExpectedResultObservable"),
                 ("deterministic", "RuleElementDeterministic"), ("allinstances", "DeterministicOutcome"), ("operator", "OperatorDomain"),
                 ("includes(self.left)", "KeyDeclared"), ("notempty", "NonEmptyParts"), ("oclistypeof", "ValueTyped")):
        if k in b:
            return n
    return "Invariant"


_NONTERM = re.compile(r"^(Atomic|Compound|Logical|Comparison|Domain|Contains$|Rule$|Expr|Value$|Literal|Term$|Key$)")


def clean_symbols(symbols: dict, allowed: set[str]) -> dict:
    """Drop grammar nonterminals / layer names; keep symbols backed by a meta-model element or label."""
    out = {}
    for layer, xs in symbols.items():
        keep = [x for x in xs if x not in CORE and not _NONTERM.match(x) and (not allowed or x in allowed)]
        out[layer] = list(dict.fromkeys(keep))
    return out


def consensus(cands: list[dict], k: int) -> dict:
    """K-consensus purification: keep entities/relations supported by >= k candidates; rest -> Others."""
    ent_votes, layer_votes, rel_votes = Counter(), defaultdict(Counter), Counter()
    for c in cands:
        for e, layer in c["entities"].items():
            ent_votes[e] += 1
            layer_votes[e][layer] += 1
        for r in set(map(tuple, c["relations"])):
            rel_votes[r] += 1
    keep = {e for e, v in ent_votes.items() if v >= k}
    entities = {e: layer_votes[e].most_common(1)[0][0] for e in sorted(keep)}
    rels = sorted({r for r, v in rel_votes.items() if v >= k and all(x in keep or x in CORE for x in (r[0], r[2]))})
    for layer in LAYERS:
        rels.append(("Rule", "contains", layer))
    others = {"entities": {e: {"layer": layer_votes[e].most_common(1)[0][0], "votes": v} for e, v in ent_votes.items() if e not in keep},
              "relations": [list(r) + [v] for r, v in rel_votes.items() if r not in set(rels)]}
    return {"entities": entities, "relations": sorted(set(rels)), "votes": dict(ent_votes), "others": others, "k": k, "n": len(cands)}


def aggregate(reps: list[dict]) -> dict:
    """Union aggregation of symbols, grammar productions and OCL invariants (deduplicated)."""
    symbols: dict[str, list[str]] = {l: [] for l in LAYERS}
    bnf: dict[str, list[str]] = {}
    ocl, seen, names = [], set(), Counter()
    for r in reps:
        for layer, xs in r.get("symbols", {}).items():
            for x in xs:
                if x and x not in symbols.setdefault(layer, []):
                    symbols[layer].append(x)
        for rule in r.get("bnf", []):
            alts = bnf.setdefault(rule["name"], [])
            for a in rule["alternatives"]:
                if a not in alts:
                    alts.append(a)
        for inv in r.get("ocl", []):
            key = re.sub(r"\W", "", inv["body"].lower())[:160]
            if key not in seen:
                seen.add(key)
                base = re.sub(r"\d+$", "", inv["name"]) or "Invariant"
                names[base] += 1
                ocl.append({**inv, "name": base if names[base] == 1 else f"{base}{names[base]}"})
    return {"symbols": symbols, "bnf": [{"name": k, "alternatives": v} for k, v in bnf.items()], "ocl": ocl}


def render_representation(rep: dict) -> tuple[str, str]:
    """Fill RAFT requirement_generation.md placeholders: (symbol definition, syntax definition)."""
    sym = ["- Logical Symbol\n  - and, or, not\n  - -> (if...then...)", "- Comparison Symbol\n  - =, !=, >, >=, <, <=, in, notin", "- Domain Symbol"]
    for layer in LAYERS:
        xs = rep["symbols"].get(layer) or []
        if xs:
            sym.append(f"  - {layer}: {', '.join(xs)}")
    if rep.get("semantics"):
        sym.append("- Semantics\n" + "\n".join(f"  - {k}: {v}" for k, v in rep["semantics"].items()))
    syn = "\n".join(f"{r['name']} ::= " + "\n    | ".join(r["alternatives"]) for r in rep["bnf"])
    return "\n".join(sym), syn


def render_ocl(rep: dict) -> str:
    return "\n\n".join(f"context {i['context']}\ninv {i['name']}:\n    {i['body']}" for i in rep["ocl"])


def keymap(rep: dict) -> dict:
    """English domain symbol -> Chinese key used by RAFT post_process / z3 generator."""
    out = {}
    for layer in LAYERS:
        for x in rep["symbols"].get(layer) or []:
            out[x] = rep.get("labels", {}).get(x) or CN.get(x) or x
    return out


def raft_assets(s: Settings) -> dict:
    """RAFT prompt templates and released knowledge artifacts (plain files in the RAFT repo)."""
    import ast
    root = s.raft_root
    rd = lambda p: (root / p).read_text(encoding="utf-8")  # noqa: E731
    ex5 = root / "experiment" / "exp5"
    pp = rd("trl/post_process.py")
    i = pp.index("keymap = {")
    km = ast.literal_eval(pp[i + len("keymap = "):pp.index("}", i) + 1])

    def quoted(path: Path, marker: str) -> str:
        src = path.read_text(encoding="utf-8")
        j = src.index(marker) + len('"content": "')
        return src[j:src.index('"', j)]

    tp = root / "testability" / "prompt"
    steps = [next(tp.glob(f"judge_testability_step{i}_prompt*.txt")).read_text(encoding="utf-8") for i in range(1, 6)]
    return {
        "prompts": {
            "meta_model": rd("data/input_prompt/meta_model_generation.md"),
            "representation": rd("data/input_prompt/testable_requirement_representation_generation.md"),
            "requirement": rd("data/input_prompt/requirement_generation.md"),
            "testability": rd("data/input_prompt/testability_determination.md"),
            "testability_steps": dict(zip(TESTABILITY_STEPS, steps)),
            "trl_traffic": rd("experiment/exp5/prompt/trl_generation_123.md"),
            "trl_power": rd("experiment/exp5/prompt/trl_generation_45.md"),
        },
        "finance": {
            "meta_model": rd("data/knowledge/meta_model.puml"),
            "representation": rd("data/knowledge/testable_requirement_representation.txt"),
            "candidates": {m: {"meta_model": rd(f"data/knowledge/meta_model_{m}.puml"),
                               "representation": rd(f"data/knowledge/testable_requirement_representation_{m}.txt")}
                           for m in ("deepseek", "gpt", "grok")},
        },
        "traffic": {m: (ex5 / "definition" / f"{m}_model_language_1.txt").read_text(encoding="utf-8") for m in ("deepseek", "gpt", "grok")},
        "power": {m: (ex5 / "definition" / f"{m}_model_language_2.txt").read_text(encoding="utf-8") for m in ("deepseek", "gpt", "grok")},
        "keymap": km,
        "corpus_tests": json.loads(rd("data/input_prompt/testcase.json")),
        "classify_prompt_crossdomain": quoted(ex5 / "rule_classify.py", '"content": "请帮我判断'),
        "translate_prompt": quoted(ex5 / "translate.py", '"content": "You are a professional translator'),
    }


def l4f_builtin(s: Settings) -> dict:
    kdir = s.llm4fin_root / "data" / "domain_knowledge"
    ck = json.loads((kdir / "classification_knowledge.json").read_text(encoding="utf-8"))
    kn = json.loads((kdir / "knowledge.json").read_text(encoding="utf-8"))
    terms = (kdir / "terms.txt").read_text(encoding="utf-8").split("\n")
    return {"state_machines": kn.get("stateMachine", []), "classification_roots": sorted({x.split(":")[0] for x in ck if ":" in x}),
            "terms": len(terms), "concepts": len([x for x in kn if x not in ("stateMachine", "authority")]),
            "classification_tree": ck}


class KnowledgeBase:
    """Persistent knowledge packs: .runtime/knowledge/<domain>.json."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()

    def path(self, domain: str) -> Path:
        return self.s.knowledge_dir / f"{domain}.json"

    def get(self, domain: str) -> dict | None:
        p = self.path(domain)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, pack: dict) -> dict:
        pack["updated"] = time.time()
        self.path(pack["domain"]).write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
        return pack

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.s.knowledge_dir.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({k: d.get(k) for k in ("domain", "title", "source", "workflow", "updated", "keywords", "provenance")}
                       | {"entities": len((d.get("meta_model") or {}).get("entities", {})),
                          "symbols": sum(len(v) for v in ((d.get("representation") or {}).get("symbols") or {}).values()),
                          "constraints": len((d.get("representation") or {}).get("ocl") or [])})
        return out

    def match(self, text: str) -> list[dict]:
        """Keyword overlap between a document/request and every registered pack."""
        low = (text or "").lower()
        res = []
        for d in self.list():
            pack = self.get(d["domain"])
            kws = pack.get("keywords") or []
            hits = [k for k in kws if k.lower() in low]
            res.append({"domain": d["domain"], "title": d["title"], "hits": hits[:12], "score": len(hits)})
        return sorted(res, key=lambda x: -x["score"])


def _tree_preview(tree: dict, depth: int = 0, max_depth: int = 4, max_children: int = 12) -> dict:
    """Bounded copy of LLM4Fin's classification knowledge tree for display."""
    if depth >= max_depth or not isinstance(tree, dict):
        return {}
    out = {}
    for i, (k, v) in enumerate(tree.items()):
        if i >= max_children:
            out[f"…(+{len(tree) - max_children})"] = {}
            break
        out[k] = _tree_preview(v, depth + 1, max_depth, max_children)
    return out


SEED_VERSION = 2  # bump when the parsers change so built-in packs are rebuilt from the original artifacts


def _stale(kb: KnowledgeBase, dom: str) -> bool:
    p = kb.get(dom)
    return not p or (p.get("source") == "builtin" and p.get("seed_version") != SEED_VERSION)


def seed_packs(kb: KnowledgeBase, l4f_builtin: dict, raft_files: dict) -> list[str]:
    """Register built-in knowledge: finance (LLM4Fin + RAFT released artifacts), traffic & power
    (RAFT exp5 three-LLM candidates, consolidated with the paper's N=3, K=2 policy)."""
    made = []
    if _stale(kb, "finance"):
        mm = parse_puml(raft_files["finance"]["meta_model"])
        rep_txt = raft_files["finance"]["representation"]
        sec = split_sections(rep_txt)
        rep = {"symbols": parse_symbols(sec["symbols"] or rep_txt, mm["entities"]), "bnf": parse_bnf(sec["syntax"] or rep_txt), "ocl": parse_ocl(rep_txt)}
        rep["labels"] = {k: v for k, v in raft_files["keymap"].items()}
        cands = [parse_puml(c["meta_model"]) for c in raft_files["finance"]["candidates"].values()]
        kb.put({"domain": "finance", "title": DOMAINS["finance"]["title"], "source": "builtin", "seed_version": SEED_VERSION, "workflow": "llm4fin",
                "keywords": DOMAINS["finance"]["kw"],
                "meta_model": {**mm, "votes": consensus(cands, 2)["votes"], "others": consensus(cands, 2)["others"], "n": len(cands)},
                "meta_model_puml": raft_files["finance"]["meta_model"], "representation": rep, "representation_text": rep_txt,
                "llm4fin": {"state_machines": l4f_builtin["state_machines"], "classification_roots": l4f_builtin["classification_roots"],
                            "terms": l4f_builtin["terms"], "concepts": l4f_builtin["concepts"],
                            "classification_tree": _tree_preview(l4f_builtin.get("classification_tree") or {})},
                "provenance": "LLM4Fin data/domain_knowledge (classification_knowledge, stateMachine, terms) + RAFT data/knowledge (meta_model.puml, testable_requirement_representation.txt)"})
        made.append("finance")
    for dom in ("traffic", "power"):
        if not _stale(kb, dom):
            continue
        cands_txt = raft_files[dom]
        mms = [parse_puml(t) for t in cands_txt.values()]
        reps = []
        for t, m in zip(cands_txt.values(), mms):
            sec = split_sections(t)
            reps.append({"symbols": parse_symbols(sec["symbols"] or t, m["entities"]) or parse_symbols(t, m["entities"]),
                         "bnf": parse_bnf(sec["syntax"] or t), "ocl": parse_ocl(sec["constraints"] or t)})
        mm = consensus(mms, 2)
        rep = aggregate(reps)
        prompt = raft_files["prompts"]["trl_traffic" if dom == "traffic" else "trl_power"]
        prompt_syms = parse_symbols(prompt)
        for layer, xs in prompt_syms.items():
            for x in xs:
                if x not in rep["symbols"].setdefault(layer, []):
                    rep["symbols"][layer].append(x)
        allowed = {e for m in mms for e in m["entities"]} | {x for xs in prompt_syms.values() for x in xs} | set(CN)
        rep["symbols"] = clean_symbols(rep["symbols"], allowed)
        rep["labels"] = {k: v for k, v in raft_files["keymap"].items()}
        kb.put({"domain": dom, "title": DOMAINS[dom]["title"], "source": "builtin", "seed_version": SEED_VERSION, "workflow": "raft", "keywords": DOMAINS[dom]["kw"],
                "meta_model": mm, "representation": rep, "trl_prompt": prompt,
                "candidates": {m: {"meta_model": parse_puml(t)} for m, t in cands_txt.items()},
                "provenance": f"RAFT experiment/exp5/definition/*_model_language_{1 if dom == 'traffic' else 2}.txt (deepseek/gpt/grok) consolidated N=3,K=2 + exp5/prompt/trl_generation_{'123' if dom == 'traffic' else '45'}.md"})
        made.append(dom)
    return made


def detect_domain(text: str, kb: KnowledgeBase) -> dict:
    """Keyword evidence per known domain; unknown when no domain has enough evidence.
    Thresholds scale with text length so short requests and long documents are both handled."""
    low = (text or "")[:60000].lower()
    scores = {}
    for d, info in DOMAINS.items():
        pack = kb.get(d) or {}
        kws = list(dict.fromkeys(info["kw"] + (pack.get("keywords") or [])))
        hits = {k: low.count(k.lower()) for k in kws if k.lower() in low}
        scores[d] = {"score": sum(min(v, 20) for v in hits.values()), "hits": sorted(hits, key=lambda k: -hits[k])[:10]}
    for p in kb.list():
        if p["domain"] in scores:
            continue
        pack = kb.get(p["domain"]) or {}
        hits = {k: low.count(k.lower()) for k in pack.get("keywords") or [] if k.lower() in low}
        scores[p["domain"]] = {"score": sum(min(v, 20) for v in hits.values()), "hits": sorted(hits, key=lambda k: -hits[k])[:10]}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1]["score"])
    best = ranked[0][0] if ranked else None
    margin = ranked[0][1]["score"] - (ranked[1][1]["score"] if len(ranked) > 1 else 0)
    need = 1 if len(low) < 300 else 2 if len(low) < 2000 else 8
    known = best is not None and scores[best]["score"] >= need and margin >= max(1, need // 2)
    return {"domain": best if known else None, "scores": scores, "confident": known}
