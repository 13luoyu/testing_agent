"""LLM4Fin worker: wraps the original pipeline (ours/main.py nlp_process + alg_process)
step by step, with the same functions, arguments and order. Runs in a subprocess."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from ..config import get_settings
from .legacy import enter_repo


def _cached(mod, attr):
    cls, cache = getattr(mod, attr), {}

    class Shim:
        @staticmethod
        def from_pretrained(path, *a, **k):
            key = (str(path), repr(sorted(k.items())))
            if key not in cache:
                cache[key] = cls.from_pretrained(path, *a, **k)
            return cache[key]

    setattr(mod, attr, Shim)


def setup() -> dict:
    s = get_settings()
    root = s.llm4fin_root
    enter_repo(root, root / "ours")
    from ours import process_sci_to_sco, process_tci_to_tco
    from ours.consistency_checking import consistency_checking
    from ours.main import add_defines
    from ours.process_knowledge import process_knowledge
    from ours.process_nl_to_sci import nl_to_sci
    from ours.process_r1_to_r2 import compose_rules_r1_r2, preprocess
    from ours.process_r2_to_r3 import compose_rules_r2_r3
    from ours.process_r3_to_testcase import testcase
    from ours.process_sco_to_tci import sco_to_tci
    from ours.process_tco_to_r1 import to_r1
    from ours.process_testcase_to_outputs import generate_dicts
    from support.generate_data_for_sequence_classification import is_id
    from transfer import mydsl_to_rules, rules_to_mydsl

    for mod, attrs in ((process_sci_to_sco, ("AutoModelForSequenceClassification", "AutoTokenizer")),
                       (process_tci_to_tco, ("AutoModelForTokenClassification", "AutoTokenizer"))):
        for a in attrs:
            _cached(mod, a)

    kdir = root / "data" / "domain_knowledge"
    ck = json.loads((kdir / "classification_knowledge.json").read_text(encoding="utf-8"))
    kn = json.loads((kdir / "knowledge.json").read_text(encoding="utf-8"))
    terms = (kdir / "terms.txt").read_text(encoding="utf-8").split("\n")
    m = s.model_dir
    sc_model, tc_model, tc_dict = str(m / "mengzi_rule_filtering"), str(m / "mengzi_rule_element_extraction"), str(m / "tc_data.dict")

    def _state(defines, vars, rules):
        return json.loads(json.dumps({"defines": defines, "vars": vars, "rules": rules}, ensure_ascii=False))

    def segment(path: str | None = None, text: str | None = None) -> dict:
        """preprocess: nl_to_sci (pdf -> sci; txt uses hybrid=is_id(first line) as in main.py)."""
        if path and path.lower().endswith(".pdf"):
            sci, setting = nl_to_sci(nl_file=path, knowledge=ck)
        else:
            data = text if text is not None else Path(path).read_text(encoding="utf-8")
            hybrid = is_id(data.strip().split("\n")[0])
            sci, setting = nl_to_sci(nl_data=data, knowledge=ck, hybrid=hybrid)
        return {"sci": sci, "setting": setting, "count": len(sci)}

    def filter_rules(sci: list, batch_size: int = 8, max_len: int = 512) -> dict:
        """rule_filter: mengzi sequence classification (0 untestable / 1 testable / 2 knowledge)."""
        sco = process_sci_to_sco.sequence_classification(copy.deepcopy(sci), sc_model, batch_size, max_len)
        return {"sco": sco, "types": dict(Counter(x["type"] for x in sco))}

    def extract(sco: list, batch_size: int = 8, max_len: int = 512) -> dict:
        """rule_element_extraction: sco_to_tci + mengzi token classification (+ algorithmic fix)."""
        tci = sco_to_tci(copy.deepcopy(sco))
        tco = process_tci_to_tco.token_classification_encoder(copy.deepcopy(tci), ck, tc_model, tc_dict, batch_size, max_len)
        return {"tci": tci, "tco": tco}

    def assemble(tco: list, setting: dict) -> dict:
        """rule_assembly: to_r1 + add_defines -> R1 (structured requirements)."""
        r1 = add_defines(to_r1(copy.deepcopy(tco), ck, terms), setting)
        defines, vars, rules = mydsl_to_rules.mydsl_to_rules(r1)
        return {"r1": r1, "rules": rules, "count": len(rules)}

    def complete(r1: str, concretize: bool = False) -> dict:
        """R1 -> R2: preprocess + compose_rules_r1_r2 (domain-knowledge completion)."""
        defines, vars, rules = mydsl_to_rules.mydsl_to_rules(r1)
        rules, vars = preprocess(rules, vars)
        n1 = len(rules)
        defines, vars, rules = compose_rules_r1_r2(defines, vars, rules, ck, concretize)
        r2 = rules_to_mydsl.rules_to_mydsl(rules_to_mydsl.r2_to_json(rules))
        return {"state": _state(defines, vars, rules), "r2": r2, "r1_count": n1, "count": len(rules)}

    def relate(state: dict) -> dict:
        """R2 -> R3: compose_rules_r2_r3 (state machine + explicit/implicit relation mining)."""
        defines, vars, rules, ic, ec, rel, irel, erel = compose_rules_r2_r3(state["defines"], state["vars"], state["rules"], kn)
        r3 = rules_to_mydsl.rules_to_mydsl(rules_to_mydsl.r3_to_json(rules))
        return {"state": _state(defines, vars, rules), "r3": r3, "count": len(rules),
                "explicit_count": ec, "implicit_count": ic, "relation": rel,
                "explicit_relation": erel, "implicit_relation": irel}

    def generate(state: dict) -> dict:
        """testcase: z3-based value generation + generate_dicts."""
        defines, vars, rules = state["defines"], state["vars"], state["rules"]
        vars = testcase(defines, vars, rules)
        out = generate_dicts(vars, rules)
        return {"testcases": out, "groups": len(out), "count": sum(len(o) for o in out)}

    def consistency(r1: str, doc: str = "doc") -> dict:
        """consistency_checking (interface.py /consistency_checking) over R1 rules with if/then."""
        defines, vars, rules = mydsl_to_rules.mydsl_to_rules(r1)
        lines, skipped = [], []
        for rid, r in rules.items():
            if not r.get("constraints") or not r.get("results"):
                skipped.append(rid)
                continue
            src = r1[r1.find(f"rule {rid}\n"):]
            block = src.split("\n\n")[0]
            lines.append(block.replace(f"rule {rid}\n", f"rule {doc}的{rid}\n", 1))
        res = consistency_checking("\n\n".join(lines) + "\n")
        for c in res:
            c["rule_ids"] = [x.split("的", 1)[-1] for x in c["rule_ids"]]
        return {"conflicts": res, "checked": len(lines), "skipped": skipped}

    def knowledge(sco: list) -> dict:
        """process_knowledge: definitions/knowledge sentences (type 2) -> key/value knowledge."""
        k, todo, _, _ = process_knowledge(copy.deepcopy(sco))
        return {"knowledge": k, "todo": todo}

    def builtin() -> dict:
        sm = kn.get("stateMachine", [])
        tops = [x for x in ck if ":" in x]
        return {"state_machines": sm, "classification_roots": sorted({x.split(":")[0] for x in tops}),
                "classification_tree": ck, "terms": len(terms), "concepts": len([x for x in kn if x not in ("stateMachine", "authority")])}

    return {"segment": segment, "filter": filter_rules, "extract": extract, "assemble": assemble,
            "complete": complete, "relate": relate, "generate": generate, "consistency": consistency,
            "knowledge": knowledge, "builtin": builtin}
