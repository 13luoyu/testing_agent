"""RAFT worker: deterministic parts of the RAFT repo (document preprocessing, mengzi
testability filter, TRL post_process, z3 test generation, built-in knowledge files).
LLM prompting steps run agent-side with the repo's own prompt files."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from collections import OrderedDict
from pathlib import Path

from ..config import get_settings
from .legacy import enter_repo


def setup() -> dict:
    s = get_settings()
    root = s.raft_root
    enter_repo(root, root)
    from experiment.exp1 import document_preprocess as dp
    from testcase import generate_testcase as gt
    from trl import post_process as pp

    clf = {}

    def _clf():
        if not clf:
            from experiment.exp1 import rule_classify as rc
            rc.set_global(str(s.model_dir / "mengzi_rule_filtering"))
            clf["m"] = rc
        return clf["m"]

    def segment(path: str | None = None, text: str | None = None, mode: str = "auto") -> dict:
        """main.py: read_pdf_to_text2 (CN) / read_pdf_to_text (EN) -> read_txt_to_json."""
        if path and path.lower().endswith(".pdf"):
            raw = dp.read_pdf_to_text2(path)
            if mode == "en" or (mode == "auto" and _cjk_ratio(raw) < 0.05):
                raw = dp.read_pdf_to_text(path)
        else:
            raw = text if text is not None else Path(path).read_text(encoding="utf-8")
        data = dp.read_txt_to_json(raw)
        for i, d in enumerate(data, 1):
            d["rid"] = f"R{i}"
        return {"rules": data, "count": len(data), "chars": len(raw)}

    def filter_rules(texts: list[str]) -> dict:
        """main.py: set_global(mengzi_rule_filtering) + classify (label 1 == testable)."""
        rc = _clf()
        return {"testable": [bool(rc.classify(t)) for t in texts]}

    def postprocess(preds: list[str], keymap: dict | None = None) -> dict:
        """trl/post_process.py, one prediction at a time so one malformed TRL cannot sink the batch."""
        saved = pp.keymap
        if keymap:
            merged = {**saved, **{k: v for k, v in keymap.items() if k and v and k not in saved}}
            pp.keymap = OrderedDict(sorted(merged.items(), key=lambda kv: -len(kv[0])))
        out, errors = [], {}
        try:
            for i, p in enumerate(preds):
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        out.append(pp.post_process([p])[0])
                except BaseException as e:  # noqa: BLE001
                    out.append("")
                    errors[i] = f"{type(e).__name__}: {e}"
        finally:
            pp.keymap = saved
        return {"trl": out, "errors": errors}

    def parse(trl: str, rule: str = "") -> dict:
        """mydsl_to_rule: syntax gate before test generation (exit(-1) on malformed TRL)."""
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                r = gt.mydsl_to_rule({"rule": rule, "predict": trl})
            return {"ok": True, "trl": r["trl"]}
        except BaseException as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}".strip()}

    def generate(items: list[dict]) -> dict:
        """testcase/generate_testcase.py: generate_testcase([{rule, predict}]).
        mydsl_to_rule parses (and de-duplicates) the whole TRL once; each parsed sub-rule then runs
        through the original generate_testcase loop on its own, so tests stay attributable to it
        (the loop treats sub-rules independently, so the concatenation equals the batch result)."""
        out, errors = [], {}
        orig = gt.mydsl_to_rule
        for i, it in enumerate(items):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    parsed = orig({"rule": it["rule"], "predict": it["predict"]})
                    subs = []
                    for sub in parsed["trl"]:
                        gt.mydsl_to_rule = lambda _t, _s=sub: {"rule": it["rule"], "trl": [copy.deepcopy(_s)]}
                        try:
                            subs.append(gt.generate_testcase([{"rule": it["rule"], "predict": ""}])[0]["testcase"])
                        finally:
                            gt.mydsl_to_rule = orig
                out.append({"trl": parsed["trl"], "subs": subs, "testcase": [t for s in subs for t in s]})
            except BaseException as e:  # noqa: BLE001
                gt.mydsl_to_rule = orig
                out.append({"trl": [], "subs": [], "testcase": []})
                errors[i] = f"{type(e).__name__}: {e}"
        return {"results": out, "errors": errors, "count": sum(len(r["testcase"]) for r in out)}

    def files() -> dict:
        """Prompt templates and released knowledge artifacts shipped with the RAFT repo."""
        rd = lambda p: (root / p).read_text(encoding="utf-8")  # noqa: E731
        ex5 = root / "experiment" / "exp5"
        return {
            "prompts": {
                "meta_model": rd("data/input_prompt/meta_model_generation.md"),
                "representation": rd("data/input_prompt/testable_requirement_representation_generation.md"),
                "requirement": rd("data/input_prompt/requirement_generation.md"),
                "testability": rd("data/input_prompt/testability_determination.md"),
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
            "keymap": dict(pp.keymap),
            "corpus_tests": json.loads(rd("data/input_prompt/testcase.json")),
            "classify_prompt_crossdomain": _exp5_classify_prompt(ex5 / "rule_classify.py"),
            "translate_prompt": _exp5_translate_prompt(ex5 / "translate.py"),
        }

    return {"segment": segment, "filter": filter_rules, "postprocess": postprocess, "parse": parse,
            "generate": generate, "files": files}


def _cjk_ratio(t: str) -> float:
    t = t[:5000]
    return sum(1 for c in t if "\u4e00" <= c <= "\u9fff") / max(1, len(t))


def _exp5_classify_prompt(p: Path) -> str:
    src = p.read_text(encoding="utf-8")
    i = src.index('"content": "请帮我判断') + len('"content": "')
    return src[i:src.index('",', i)]


def _exp5_translate_prompt(p: Path) -> str:
    src = p.read_text(encoding="utf-8")
    i = src.index('"content": "You are a professional translator') + len('"content": "')
    return src[i:src.index('"', i)]
