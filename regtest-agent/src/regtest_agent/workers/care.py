"""CARE worker: mirrors reuse/interface.py. Algorithmic endpoints are the original
endpoint functions (loaded with stub flask); requirement_generation is split at its
rule_formalization call, which is served by the agent-side stand-in (GLM4-LoRA
weights are not available) through a prediction cache."""
from __future__ import annotations

import copy
from pathlib import Path

from ..config import get_settings
from .legacy import call_endpoint, enter_repo, load_interface

PRED: dict[str, str] = {}


class MissingPrediction(RuntimeError):
    pass


def dedup_ids(final: list[list[dict]], origin: dict[int, str]) -> tuple[dict, list]:
    """CARE remaps surviving old tests onto new rule ids and numbers newly generated tests from _1, so ids can collide
    (new vs reused, and two old tests remapped onto the same id). Reused tests (id(tc) in origin) claim ids first;
    every later duplicate moves to the next free index of its rule. Returns ({new id: old id}, [[from, to]])."""
    used, renumbered, kept = set(), [], {}
    for reused in (True, False):
        for g in final:
            for tc in g:
                if (id(tc) in origin) != reused:
                    continue
                if tc["testid"] in used:
                    n = 1
                    while f"{tc['rule']}_{n}" in used:
                        n += 1
                    renumbered.append([tc["testid"], f"{tc['rule']}_{n}"])
                    tc["testid"] = f"{tc['rule']}_{n}"
                used.add(tc["testid"])
                if reused:
                    kept[tc["testid"]] = origin[id(tc)]
    return kept, renumbered


def setup() -> dict:
    s = get_settings()
    root = s.care_root
    enter_repo(root, root / "reuse", [root / "reuse"])
    up = s.runtime / "care_uploads"
    up.mkdir(parents=True, exist_ok=True)
    log = s.logs_dir / "care_interface.log"
    ns = load_interface(root / "reuse" / "interface.py", "care_interface", [
        ("app.config['UPLOAD_FOLDER'] = './download_files'", f"app.config['UPLOAD_FOLDER'] = {str(up)!r}"),
        ('sc_model_path = "../model/trained/mengzi_rule_filtering"', f"sc_model_path = {str(s.model_dir / 'mengzi_rule_filtering')!r}"),
        ("os.makedirs('./download_files', exist_ok=True)", "os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)"),
        ('log = open("interface.log", "w", encoding="utf-8")', f'log = open({str(log)!r}, "a", encoding="utf-8")'),
    ])

    def rule_formalization(fi, model_name_or_path=None, setting=None, **kw):
        fo, missing = copy.deepcopy(fi), []
        for item in fo:
            p = PRED.get(item["text"])
            if p is None:
                missing.append(item.get("id"))
            item["prediction"] = p
        if missing:
            raise MissingPrediction(f"no formalization for rules {missing[:10]}")
        return fo

    ns["rule_formalization"] = rule_formalization
    nl_to_sci, sequence_classification, select_rules = ns["nl_to_sci"], ns["sequence_classification"], ns["select_rules"]
    to_r, Rrule_transfer = ns["to_r"], ns["Rrule_transfer"]
    ck, sc_model = ns["classification_knowledge"], ns["sc_model_path"]

    def prepare(path: str | None = None, text: str | None = None) -> dict:
        """requirement_generation, part 1: nl_to_sci -> sequence_classification -> select_rules."""
        if path and path.lower().endswith(".pdf"):
            sci, mv = nl_to_sci(nl_file=path, knowledge=ck)
        else:
            data = text if text is not None else Path(path).read_text(encoding="utf-8")
            sci, mv = nl_to_sci(nl_data=data, knowledge=ck)
        sco = sequence_classification(sci, sc_model)
        sco_copy = copy.deepcopy(sco)
        fi = select_rules(sco)
        return {"fi": fi, "sco": sco_copy, "market_variety": mv, "sci_count": len(sci)}

    def finish(fo: list) -> dict:
        """requirement_generation, part 2: to_r(fix=True) -> Rrule_transfer; rules = [{id, text}]."""
        r1 = to_r(fo, fix=True)
        return {"rules": [{"id": x["id"], "text": x["text"]} for x in fo], "requirements": Rrule_transfer(r1), "r1": r1}

    def scenarios(requirements, sco: list, market_variety: dict) -> dict:
        return call_endpoint(ns, "scenario_generation", {"requirements": requirements, "sco": sco, "market_variety": market_variety})

    def align(scenarios, testcases: list) -> dict:
        return call_endpoint(ns, "testcase_align", {"scenarios": scenarios, "testcases": testcases})

    def diff(old_texts: list, new_texts: list, old_scenarios, new_scenarios) -> dict:
        return call_endpoint(ns, "change_identify", {"old_texts": old_texts, "new_texts": new_texts,
                                                      "old_scenarios": old_scenarios, "new_scenarios": new_scenarios})

    def impact(old_scenarios, to_delete_rules: list, old_relation: dict) -> dict:
        return call_endpoint(ns, "impact_analysis", {"old_scenarios": old_scenarios, "to_delete_rules": to_delete_rules,
                                                      "old_relation": old_relation})

    def update(new_texts, new_scenarios, to_delete_rules, to_add_rules, old_relation, old_testcases, new_map,
               new_sco, new_market_variety, predictions: dict) -> dict:
        """testcase_update; reused tests are tracked by object identity across the in-place update."""
        PRED.update(predictions)
        params = copy.deepcopy({"new_texts": new_texts, "new_scenarios": new_scenarios, "to_delete_rules": to_delete_rules,
                                "to_add_rules": to_add_rules, "old_relation": old_relation, "old_testcases": old_testcases,
                                "new_map": new_map, "new_sco": new_sco, "new_market_variety": new_market_variety})
        origin = {id(tc): tc["testid"] for g in params["old_testcases"] for tc in g}
        alive = [tc for g in params["old_testcases"] for tc in g]  # keep ids unique during the update
        data = call_endpoint(ns, "testcase_update", params)
        final = data["testcases"]
        kept, renumbered = dedup_ids(final, origin)
        survived = set(kept.values())
        deleted = [t for t in origin.values() if t not in survived]
        del alive
        return {"testcases": final, "reused": kept, "deleted": deleted, "renumbered": renumbered}

    def generate(scenarios) -> dict:
        out = ns["process_r3_to_testcase"](ns["Rrule_back"](scenarios))
        return {"testcases": out, "count": sum(len(g) for g in out)}

    def remember(predictions: dict) -> dict:
        PRED.update(predictions)
        return {"cached": len(PRED)}

    return {"prepare": prepare, "finish": finish, "scenarios": scenarios, "align": align, "diff": diff,
            "impact": impact, "update": update, "generate": generate, "remember": remember}
