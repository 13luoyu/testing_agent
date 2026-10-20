"""Common tools: document intake, domain detection, knowledge lookup."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..knowledge import DOMAINS, KnowledgeBase, detect_domain
from .base import ToolContext, ToolFailed, tool


def read_document(path: str) -> dict:
    p = Path(path)
    ext = p.suffix.lower()
    pages = None
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(p) as pdf:
            pages = len(pdf.pages)
            text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    elif ext == ".docx":
        import docx
        text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    else:
        raw = p.read_bytes()
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ToolFailed(f"无法识别文件编码: {p.name}")
    return {"text": text, "pages": pages, "ext": ext}


def lang_of(text: str) -> str:
    t = text[:20000]
    kana = sum(1 for c in t if "\u3040" <= c <= "\u30ff")
    cjk = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in t if c.isascii() and c.isalpha())
    if kana > 50:
        return "ja"
    if cjk > latin * 0.3:
        return "zh"
    return "en"


def load_testcases(path: str) -> list[list[dict]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("testcases") or data.get("data") or list(data.values())
    if data and isinstance(data[0], dict):
        groups: dict[str, list] = {}
        for i, tc in enumerate(data):
            tc.setdefault("testid", f"{tc.get('rule', 'T')}_{i + 1}")
            groups.setdefault(tc.get("rule", tc["testid"]), []).append(tc)
        data = list(groups.values())
    out = []
    for g in data:
        g = [dict(tc) for tc in g if isinstance(tc, dict)]
        for j, tc in enumerate(g):
            tc["rule"] = str(tc.get("rule", "")) or f"T{len(out) + 1}"
            tc.setdefault("testid", f"{tc['rule']}_{j + 1}")
            for k, v in list(tc.items()):
                if not isinstance(v, str):
                    tc[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        if g:
            out.append(g)
    if not out:
        raise ToolFailed("测试用例文件为空或格式不正确（需为 [[{rule, testid, 要素...}]] 或 [{...}]）")
    return out


@tool("doc.ingest", "读取文档", "common", "pdfplumber / python-docx", "local",
      "读取上传的规则文档，抽取全文，计算指纹并查询记忆中是否处理过同一文档", ["path"], ["doc_<role>"])
def doc_ingest(ctx: ToolContext, path: str, name: str = "", role: str = "main") -> dict:
    d = read_document(path)
    text = d["text"]
    if len(text.strip()) < 20:
        raise ToolFailed(f"文档 {name or Path(path).name} 未抽取到有效文本（可能是扫描件）")
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    seen = ctx.memory.doc_runs(sha) if ctx.memory else []
    doc = {"name": name or Path(path).name, "path": path, "sha": sha, "chars": len(text), "pages": d["pages"],
           "lang": lang_of(text), "text": text, "seen": seen}
    ctx.save(f"doc_{role}", doc)
    return {"summary": {"文档": doc["name"], "页数": d["pages"], "字符数": len(text), "语言": doc["lang"],
                        "历史处理次数": len(seen)}, "doc": {k: v for k, v in doc.items() if k != "text"}}


@tool("tests.ingest", "读取历史测试用例", "common", "json", "local",
      "读取用户提供的原测试用例（CARE testcase.json 格式或扁平列表）", ["path"], ["tests_old"])
def tests_ingest(ctx: ToolContext, path: str, name: str = "") -> dict:
    groups = load_testcases(path)
    ctx.save("tests_old", {"name": name or Path(path).name, "path": path, "testcases": groups})
    keys = sorted({k for g in groups for tc in g for k in tc if k not in ("rule", "testid")})
    return {"summary": {"文件": name or Path(path).name, "用例组": len(groups), "用例数": sum(len(g) for g in groups),
                        "要素": keys[:12]}}


@tool("tests.minimize", "测试精简（成对覆盖）", "common", "regtest_agent.minimize · 2-wise set cover", "local",
      "对因枚举笛卡尔积而膨胀的用例组，选取覆盖全部观测取值对且保留正/反例的最小子集；全量用例仍为准，精简版为附加视图", ["tests"], ["tests_min"])
def tests_minimize(ctx: ToolContext, min_size: int = 4) -> dict:
    from ..minimize import minimize
    t = ctx.load("tests")
    res = minimize(t.get("testcases", []), min_size=min_size)
    ctx.save("tests_min", {"workflow": t.get("workflow"), "testcases": res["testcases"],
                           "before": res["before"], "after": res["after"], "reduction": res["reduction"]})
    return {"summary": {"精简前": res["before"], "精简后": res["after"], "缩减": f"{res['reduction']:.0%}",
                        "精简用例组": res["groups_reduced"]}}


DOMAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "is_new": {"type": "boolean"},
        "slug": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,30}$"},
        "title": {"type": "string", "maxLength": 30},
        "keywords": {"type": "array", "items": {"type": "string", "maxLength": 20}, "maxItems": 12},
        "evidence": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 5},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["domain", "is_new", "slug", "title", "keywords", "evidence", "reason"],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def _hint_agrees(hint: str, domain: str | None, kb: KnowledgeBase) -> bool:
    """True when there is no hint, or the user's hint names the keyword-detected domain."""
    if not hint:
        return True
    if not domain:
        return False
    pack = kb.get(domain) or {}
    h = _norm(hint)
    words = [pack.get("title", ""), domain, *DOMAINS.get(domain, {}).get("kw", []), *(pack.get("keywords") or [])]
    return any(w and (_norm(w) in h or h in _norm(w)) for w in words if len(_norm(w)) >= 2)


@tool("domain.detect", "识别领域", "common", "keyword evidence + local LLM", "local-llm",
      "基于关键词证据判断文档所属领域；证据不足时由本地模型给出领域与原文证据，证据必须能在原文中找到", ["doc_<role>"], ["domain"])
def domain_detect(ctx: ToolContext, role: str = "main", hint: str = "") -> dict:
    doc = ctx.load(f"doc_{role}")
    kb = KnowledgeBase()
    kw = detect_domain(doc["text"], kb)
    result = {"domain": kw["domain"], "method": "keywords", "scores": kw["scores"], "evidence": [], "is_new": False,
              "hits": kw["scores"].get(kw["domain"] or "", {}).get("hits", [])}
    if role == "main" and (not kw["confident"] or not _hint_agrees(hint, kw["domain"], kb)):
        known = [p["domain"] for p in kb.list()]
        schema = json.loads(json.dumps(DOMAIN_SCHEMA))
        schema["properties"]["domain"]["enum"] = known + ["new"]
        sample = doc["text"][:6000]
        msgs = [{"role": "system", "content": "你是法规与标准文档分析专家。判断文档属于哪个已知领域；若都不属于，domain 取 new，并给出新领域的英文 slug、中文名和该领域的关键词。"
                 "evidence 必须是从文档中逐字摘录的短语（每条不超过30字），不得改写或编造；keywords 必须是文档中出现过的词。"},
                {"role": "user", "content": f"已知领域：{json.dumps({d: (kb.get(d) or {}).get('title', d) for d in known}, ensure_ascii=False)}\n"
                                            f"用户提示：{hint or '无'}\n文档名：{doc['name']}\n文档开头：\n{sample}"}]
        out = ctx.llm.json(msgs, schema, max_tokens=600, kind="domain.detect")
        ev = [e for e in out["evidence"] if _norm(e) and _norm(e) in _norm(doc["text"])]
        kws = [k for k in out["keywords"] if _norm(k) and _norm(k) in _norm(doc["text"])]
        if ev:
            if out["domain"] == "new" or out["is_new"]:
                slug = out["slug"] if out["slug"] not in known else out["slug"] + "_x"
                result.update(domain=slug, is_new=True, title=out["title"], keywords=kws or [out["title"]], method="local-llm", evidence=ev, reason=out["reason"])
            else:
                result.update(domain=out["domain"], method="local-llm", evidence=ev, reason=out["reason"])
        elif kw["domain"] is None:
            result.update(domain=None, method="undetermined", reason="关键词与模型证据均不足")
    if result["domain"] and not result.get("title"):
        result["title"] = (kb.get(result["domain"]) or {}).get("title") or DOMAINS.get(result["domain"], {}).get("title", result["domain"])
    if role == "main":
        ctx.save("domain", result)
    return {"summary": {"领域": result.get("title") or "未确定", "方式": result["method"], "新领域": result["is_new"],
                        "证据": (result["evidence"] or kw["scores"].get(result["domain"] or "", {}).get("hits", []))[:4]}, "domain": result}


@tool("knowledge.lookup", "查询领域知识", "common", "knowledge base", "local",
      "检查知识库中是否已有该领域的元模型 / 需求表示 / 可测试性约束", ["domain"], ["knowledge"])
def knowledge_lookup(ctx: ToolContext, domain: str | None = None) -> dict:
    domain = domain or (ctx.load("domain", {}) or {}).get("domain")
    pack = KnowledgeBase().get(domain) if domain else None
    info = {"domain": domain, "found": bool(pack)}
    if pack:
        rep = pack.get("representation") or {}
        info.update(title=pack.get("title"), source=pack.get("source"), workflow=pack.get("workflow"),
                    entities=len((pack.get("meta_model") or {}).get("entities", {})),
                    symbols=sum(len(v) for v in (rep.get("symbols") or {}).values()), constraints=len(rep.get("ocl") or []),
                    provenance=pack.get("provenance"))
    ctx.save("knowledge", info)
    s = {"领域": domain, "命中": "是" if pack else "否"}
    if pack:
        s.update({"元模型要素": info["entities"], "领域符号": info["symbols"], "可测试性约束": info["constraints"], "来源": pack.get("source")})
    return {"summary": s, "knowledge": info}
